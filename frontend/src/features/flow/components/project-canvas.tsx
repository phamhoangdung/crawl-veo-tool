import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Background,
  Controls,
  ReactFlow,
  type Edge,
  type Node,
  type NodeChange,
} from '@xyflow/react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import axios from 'axios'
import { Plus, Redo2, Save, Undo2 } from 'lucide-react'
import { toast } from 'sonner'
import {
  addScene,
  deleteScene,
  exportProjectToLibrary,
  generateProjectScene,
  getProject,
  getProjectCostEstimate,
  projectOutputUrl,
  saveProjectCanvas,
  startProjectRender,
  updateScene,
  type SceneRead,
} from '@/lib/api'
import { Button } from '@/components/ui/button'
import {
  SCENE_NODE_WIDTH,
  autoLayoutLinear,
  edgesFromOrder,
  validateGraph,
} from '../graph'
import { useFlowStore, type NodePositions } from '../store'
import { OutputNode, type OutputNodeData } from './output-node'
import { SceneNode, type SceneNodeData } from './scene-node'
import { SceneSettingsDialog, type ScenePatch } from './scene-settings-dialog'

const OUTPUT_NODE_ID = 'output'
const nodeTypes = { scene: SceneNode, output: OutputNode }

function apiDetail(error: unknown): string | null {
  return axios.isAxiosError(error)
    ? ((error.response?.data as { detail?: string })?.detail ?? null)
    : null
}

export function ProjectCanvas({ projectId }: { projectId: number }) {
  const queryClient = useQueryClient()
  const [settingsSceneId, setSettingsSceneId] = useState<number | null>(null)
  const [generatingId, setGeneratingId] = useState<number | null>(null)
  // Chỉ giữ prompt ĐANG SỬA, không copy toàn bộ từ server — dữ liệu gốc luôn
  // đọc thẳng từ query, tránh hai nguồn sự thật lệch nhau.
  const [prompts, setPrompts] = useState<Record<number, string>>({})

  const positions = useFlowStore((s) => s.positions)
  const dirty = useFlowStore((s) => s.dirty)
  const canUndo = useFlowStore((s) => s.past.length > 0)
  const canRedo = useFlowStore((s) => s.future.length > 0)

  const project = useQuery({
    queryKey: ['project', projectId],
    queryFn: () => getProject(projectId),
    // Trong lúc dựng, poll để thấy cảnh nào xong — SSE chỉ đẩy tiến độ tổng.
    refetchInterval: (query) => (query.state.data?.is_rendering ? 2000 : false),
  })

  const costEstimate = useQuery({
    queryKey: ['project-cost', projectId],
    queryFn: () => getProjectCostEstimate(projectId),
  })

  const scenes = useMemo(() => project.data?.scenes ?? [], [project.data])
  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['project', projectId] })
    // Đổi cảnh (thời lượng, ảnh tĩnh vs video AI) là đổi chi phí — không làm mới
    // thì con số trên node output đứng yên và gây hiểu nhầm.
    queryClient.invalidateQueries({ queryKey: ['project-cost', projectId] })
  }

  // Nạp vị trí từ server một lần cho mỗi bộ cảnh; cảnh mới chưa có vị trí thì
  // xếp ngang tự động. Chỉ ghi vào store (ngoài React) nên không gây cascading
  // render như setState trong effect.
  useEffect(() => {
    if (scenes.length === 0) return
    const fallback = autoLayoutLinear(scenes.length)
    const next: NodePositions = {}
    scenes.forEach((scene, index) => {
      next[scene.id] =
        scene.canvas_x || scene.canvas_y
          ? { x: scene.canvas_x, y: scene.canvas_y }
          : fallback[index]
    })
    useFlowStore.getState().setPositions(next)
  }, [scenes])

  const savePrompt = useMutation({
    mutationFn: ({ sceneId, prompt }: { sceneId: number; prompt: string }) =>
      updateScene(sceneId, { prompt }),
    onSuccess: invalidate,
  })

  const patchScene = useMutation({
    mutationFn: ({ sceneId, patch }: { sceneId: number; patch: ScenePatch }) =>
      updateScene(sceneId, patch),
    onSuccess: () => {
      invalidate()
      setSettingsSceneId(null)
      toast.success('Đã lưu tuỳ chọn cảnh.')
    },
    onError: (error) => toast.error(apiDetail(error) ?? 'Không lưu được tuỳ chọn.'),
  })

  const generate = useMutation({
    mutationFn: (sceneId: number) => generateProjectScene(sceneId),
    onMutate: (sceneId) => setGeneratingId(sceneId),
    onSettled: () => setGeneratingId(null),
    onSuccess: () => {
      invalidate()
      toast.success('Đã sinh xong cảnh.')
    },
    onError: (error) => toast.error(apiDetail(error) ?? 'Không sinh được cảnh.'),
  })

  const append = useMutation({
    mutationFn: () => addScene(projectId, { prompt: '' }),
    onSuccess: invalidate,
  })

  const removeScene = useMutation({
    mutationFn: deleteScene,
    onSuccess: () => {
      invalidate()
      toast.success('Đã xoá cảnh.')
    },
  })

  const saveCanvas = useMutation({
    mutationFn: () =>
      saveProjectCanvas(
        projectId,
        Object.entries(useFlowStore.getState().positions).map(([id, p]) => ({
          scene_id: Number(id),
          x: p.x,
          y: p.y,
        }))
      ),
    onSuccess: () => {
      useFlowStore.getState().markSaved()
      toast.success('Đã lưu bố cục canvas.')
    },
  })

  const render = useMutation({
    mutationFn: () => startProjectRender(projectId),
    onSuccess: (result) => {
      invalidate()
      toast.success(result.message)
    },
    onError: (error) => toast.error(apiDetail(error) ?? 'Không dựng được video.'),
  })

  const exportToLibrary = useMutation({
    mutationFn: () => exportProjectToLibrary(projectId),
    onSuccess: (result) => {
      toast.success(
        `Đã thêm "${result.name}" vào kho — mở được trong Timeline Editor để thêm lồng tiếng/phụ đề.`
      )
    },
    onError: (error) => toast.error(apiDetail(error) ?? 'Không thêm được vào kho.'),
  })

  const { mutate: generateMutate } = generate
  const { mutate: savePromptMutate } = savePrompt
  const { mutate: removeSceneMutate } = removeScene
  const { mutate: renderMutate } = render
  const { mutate: exportMutate } = exportToLibrary

  const handlePromptChange = useCallback((sceneId: number, prompt: string) => {
    setPrompts((current) => ({ ...current, [sceneId]: prompt }))
  }, [])

  const nodes: Node[] = useMemo(() => {
    const sceneNodes: Node[] = scenes.map((scene, index) => ({
      id: String(scene.id),
      type: 'scene',
      position: positions[scene.id] ?? { x: index * 320, y: 0 },
      data: {
        scene: { ...scene, prompt: prompts[scene.id] ?? scene.prompt },
        isFirst: index === 0,
        isGenerating: generatingId === scene.id,
        onPromptChange: handlePromptChange,
        onGenerate: (id: number) => {
          const draft = prompts[id]
          const original = scenes.find((s) => s.id === id)?.prompt
          // Prompt sửa trên node chưa lưu — lưu trước rồi mới sinh, nếu không
          // backend vẫn dùng prompt cũ.
          if (draft !== undefined && draft !== original) {
            savePromptMutate(
              { sceneId: id, prompt: draft },
              { onSuccess: () => generateMutate(id) }
            )
            return
          }
          generateMutate(id)
        },
        onDelete: (id: number) => removeSceneMutate(id),
        onOpenSettings: setSettingsSceneId,
      } satisfies SceneNodeData,
    }))

    const missingClips = scenes.filter((s) => s.clip_asset_id === null).length
    const outputData: OutputNodeData = {
      isRendering: project.data?.is_rendering ?? false,
      hasOutput: Boolean(project.data?.rendered_path),
      canRender: scenes.length > 0,
      blockingReason:
        scenes.length === 0
          ? 'Thêm ít nhất 1 cảnh.'
          : missingClips > 0
            ? `${missingClips} cảnh chưa có clip — bấm dựng sẽ tự sinh nốt.`
            : null,
      estimatedCostUsd: costEstimate.data?.total_cost_usd ?? null,
      freeScenes: costEstimate.data?.free_scenes ?? 0,
      pendingScenes: costEstimate.data?.pending_scenes ?? 0,
      isExporting: exportToLibrary.isPending,
      onRender: () => renderMutate(),
      onOpenOutput: () => window.open(projectOutputUrl(projectId), '_blank'),
      onExportToLibrary: () => exportMutate(),
    }

    const lastPosition =
      scenes.length > 0
        ? (positions[scenes[scenes.length - 1].id] ?? { x: scenes.length * 320, y: 0 })
        : { x: 0, y: 0 }

    return [
      ...sceneNodes,
      {
        id: OUTPUT_NODE_ID,
        type: 'output',
        // Sát hơn node cảnh (260px + 40 khoảng hở): để 320 thì node output rơi
        // ra ngoài vùng `fitView` tính được và bị cắt mất nút bấm.
        position: { x: lastPosition.x + 300, y: lastPosition.y + 60 },
        data: outputData,
        draggable: false,
        // Đặt width lên chính node wrapper: style bên trong component không
        // làm wrapper giãn ra, nên `fitView` đo thiếu và node lọt ra mép.
        style: { width: SCENE_NODE_WIDTH },
      },
    ]
  }, [
    scenes,
    positions,
    prompts,
    generatingId,
    project.data,
    costEstimate.data,
    // Cờ pending phải nằm trong deps, nếu không nút "Đang thêm..." không bao giờ hiện.
    exportToLibrary.isPending,
    handlePromptChange,
    // Chỉ phụ thuộc hàm `mutate` (ổn định về tham chiếu), không phải cả object
    // useMutation — object đổi mỗi lần render nên useMemo sẽ mất tác dụng.
    generateMutate,
    savePromptMutate,
    removeSceneMutate,
    renderMutate,
    exportMutate,
    projectId,
  ])

  // Thứ tự cảnh là `order_index` ở backend — canvas chỉ vẽ lại cho dễ nhìn.
  const edges: Edge[] = useMemo(() => {
    const chain = edgesFromOrder(scenes.map((s) => s.id))
    const sceneEdges: Edge[] = chain.map((e) => {
      const target = scenes.find((s) => String(s.id) === e.target)
      return {
        id: `${e.source}-${e.target}`,
        source: e.source,
        target: e.target,
        animated: target?.chain_from_previous ?? false,
        label: target?.transition_in === 'fade' ? 'fade' : undefined,
      }
    })
    if (scenes.length > 0) {
      sceneEdges.push({
        id: `last-output`,
        source: String(scenes[scenes.length - 1].id),
        target: OUTPUT_NODE_ID,
      })
    }
    return sceneEdges
  }, [scenes])

  const validation = useMemo(
    () =>
      validateGraph(
        scenes.map((s) => ({ id: String(s.id), position: positions[s.id] ?? { x: 0, y: 0 } })),
        edgesFromOrder(scenes.map((s) => s.id))
      ),
    [scenes, positions]
  )

  const onNodesChange = useCallback((changes: NodeChange[]) => {
    for (const change of changes) {
      if (change.type === 'position' && change.position && change.id !== OUTPUT_NODE_ID) {
        useFlowStore
          .getState()
          .moveNode(Number(change.id), change.position.x, change.position.y)
      }
    }
  }, [])

  const settingsScene: SceneRead | null =
    scenes.find((s) => s.id === settingsSceneId) ?? null

  return (
    <div className='relative h-[calc(100vh-12rem)] w-full rounded-lg border'>
      <div className='absolute top-2 left-2 z-10 flex flex-wrap items-center gap-1.5'>
        <Button size='sm' variant='secondary' className='gap-1' onClick={() => append.mutate()}>
          <Plus className='size-3.5' />
          Thêm cảnh
        </Button>
        <Button
          size='sm'
          variant='secondary'
          className='gap-1'
          onClick={() => useFlowStore.getState().undo()}
          disabled={!canUndo}
        >
          <Undo2 className='size-3.5' />
          Hoàn tác
        </Button>
        <Button
          size='sm'
          variant='secondary'
          className='gap-1'
          onClick={() => useFlowStore.getState().redo()}
          disabled={!canRedo}
        >
          <Redo2 className='size-3.5' />
          Làm lại
        </Button>
        <Button
          size='sm'
          variant={dirty ? 'default' : 'secondary'}
          className='gap-1'
          onClick={() => saveCanvas.mutate()}
          disabled={!dirty || saveCanvas.isPending}
        >
          <Save className='size-3.5' />
          {dirty ? 'Lưu bố cục' : 'Đã lưu'}
        </Button>
      </div>

      {!validation.ok && (
        <div className='bg-destructive/10 text-destructive absolute right-2 bottom-2 z-10 max-w-sm rounded-md p-2 text-xs'>
          {validation.errors.join(' ')}
        </div>
      )}

      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        onNodesChange={onNodesChange}
        onNodeDragStart={() => useFlowStore.getState().beginGesture()}
        onNodeDragStop={() => useFlowStore.getState().endGesture()}
        // `fitView` lúc mount đo khi node chưa có kích thước thật nên luôn hụt
        // vài chục pixel; `onInit` cho instance để fit lại sau khi node render xong.
        onInit={(instance) => {
          requestAnimationFrame(() =>
            instance.fitView({ padding: 0.2, maxZoom: 0.8 })
          )
        }}
        minZoom={0.2}
        proOptions={{ hideAttribution: true }}
      >
        <Background />
        <Controls />
      </ReactFlow>

      <SceneSettingsDialog
        scene={settingsScene}
        isFirst={settingsScene?.order_index === 0}
        onSave={(sceneId, patch) => patchScene.mutate({ sceneId, patch })}
        onOpenChange={(open) => !open && setSettingsSceneId(null)}
      />
    </div>
  )
}
