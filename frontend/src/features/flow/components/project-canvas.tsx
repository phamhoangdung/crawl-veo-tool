import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Background,
  Controls,
  ReactFlow,
  type Connection,
  type Edge,
  type EdgeChange,
  type Node,
  type NodeChange,
} from '@xyflow/react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import axios from 'axios'
import { Plus, Redo2, Save, Undo2, UserPlus } from 'lucide-react'
import { toast } from 'sonner'
import {
  addScene,
  deleteScene,
  exportProjectToLibrary,
  generateProjectScene,
  getCharacterReferences,
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
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  CHARACTER_NODE_PREFIX,
  SCENE_NODE_WIDTH,
  autoLayoutLinear,
  characterEdgesFromMentions,
  edgesFromOrder,
  parseMentions,
  validateGraph,
} from '../graph'
import { useFlowStore, type NodePositions } from '../store'
import { CharacterNode, type CharacterNodeData } from './character-node'
import { OutputNode, type OutputNodeData } from './output-node'
import { SceneNode, type SceneNodeData } from './scene-node'
import { SceneSettingsDialog, type ScenePatch } from './scene-settings-dialog'

const OUTPUT_NODE_ID = 'output'
const nodeTypes = { scene: SceneNode, output: OutputNode, character: CharacterNode }

function apiDetail(error: unknown): string | null {
  return axios.isAxiosError(error)
    ? ((error.response?.data as { detail?: string })?.detail ?? null)
    : null
}

/** Vị trí node nhân vật trên canvas chỉ là tiện ích hiển thị — nguồn sự thật
 *  của việc "nhân vật nào ở cảnh nào" là @mention trong text prompt (đã lưu ở
 *  backend qua Scene.prompt). Vì vậy lưu cục bộ theo trình duyệt là đủ, không
 *  cần thêm bảng/field backend cho riêng việc này. */
function characterCanvasKey(projectId: number): string {
  return `flow-character-canvas:${projectId}`
}

function loadCharacterCanvas(projectId: number): NodePositions {
  try {
    const raw = localStorage.getItem(characterCanvasKey(projectId))
    return raw ? (JSON.parse(raw) as NodePositions) : {}
  } catch {
    return {}
  }
}

function saveCharacterCanvas(projectId: number, positions: NodePositions): void {
  try {
    localStorage.setItem(characterCanvasKey(projectId), JSON.stringify(positions))
  } catch {
    // Chỉ là vị trí hiển thị — mất cũng không ảnh hưởng dữ liệu thật.
  }
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

  const characters = useQuery({
    queryKey: ['ai-studio', 'character-references'],
    queryFn: getCharacterReferences,
  })

  // Node nhân vật đặt trên canvas — chỉ lưu cục bộ (xem ghi chú ở helper phía
  // trên), khởi tạo 1 lần từ localStorage vì component remount mỗi khi đổi dự án.
  const [characterPositions, setCharacterPositions] = useState<NodePositions>(() =>
    loadCharacterCanvas(projectId)
  )
  const [placedCharacterIds, setPlacedCharacterIds] = useState<number[]>(() =>
    Object.keys(loadCharacterCanvas(projectId)).map(Number)
  )

  useEffect(() => {
    saveCharacterCanvas(projectId, characterPositions)
  }, [projectId, characterPositions])

  const addCharacterToCanvas = useCallback(
    (characterId: number) => {
      setPlacedCharacterIds((current) =>
        current.includes(characterId) ? current : [...current, characterId]
      )
      setCharacterPositions((current) =>
        current[characterId]
          ? current
          : { ...current, [characterId]: { x: -320, y: placedCharacterIds.length * 140 } }
      )
    },
    [placedCharacterIds.length]
  )

  const removeCharacterFromCanvas = useCallback((characterId: number) => {
    setPlacedCharacterIds((current) => current.filter((id) => id !== characterId))
    setCharacterPositions((current) => {
      const { [characterId]: _removed, ...rest } = current
      return rest
    })
  }, [])

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

    const characterNodes: Node[] = placedCharacterIds.flatMap((id, index) => {
      const character = characters.data?.find((c) => c.id === id)
      if (!character) return []
      return [
        {
          id: `${CHARACTER_NODE_PREFIX}${id}`,
          type: 'character',
          position: characterPositions[id] ?? { x: -320, y: index * 140 },
          data: {
            character,
            onRemove: removeCharacterFromCanvas,
          } satisfies CharacterNodeData,
        },
      ]
    })

    const lastPosition =
      scenes.length > 0
        ? (positions[scenes[scenes.length - 1].id] ?? { x: scenes.length * 320, y: 0 })
        : { x: 0, y: 0 }

    return [
      ...sceneNodes,
      ...characterNodes,
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
    placedCharacterIds,
    characters.data,
    characterPositions,
    removeCharacterFromCanvas,
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

  // Cạnh nhân vật → cảnh không phải trạng thái riêng — suy ra từ @mention có
  // trong prompt, chỉ vẽ cho nhân vật đang có mặt trên canvas.
  const characterEdges: Edge[] = useMemo(() => {
    const placedCharacters = (characters.data ?? []).filter((c) =>
      placedCharacterIds.includes(c.id)
    )
    return characterEdgesFromMentions(scenes, placedCharacters).map((e) => ({
      id: `${e.source}->${e.target}`,
      source: e.source,
      target: e.target,
      targetHandle: 'character',
    }))
  }, [scenes, characters.data, placedCharacterIds])

  const allEdges = useMemo(() => [...edges, ...characterEdges], [edges, characterEdges])

  // Kéo cạnh từ node nhân vật vào handle "character" của 1 cảnh = chèn @tên
  // vào prompt cảnh đó — không lưu cạnh riêng, prompt là nguồn sự thật.
  const onConnect = useCallback(
    (connection: Connection) => {
      const isCharacterMention =
        connection.targetHandle === 'character' &&
        connection.source.startsWith(CHARACTER_NODE_PREFIX)
      if (!isCharacterMention) return
      const characterId = Number(connection.source.slice(CHARACTER_NODE_PREFIX.length))
      const character = characters.data?.find((c) => c.id === characterId)
      const sceneId = Number(connection.target)
      const scene = scenes.find((s) => s.id === sceneId)
      if (!character || !scene) return

      const currentPrompt = prompts[sceneId] ?? scene.prompt
      if (parseMentions(currentPrompt).includes(character.name)) {
        toast.info(`Cảnh này đã có @${character.name} rồi.`)
        return
      }
      const nextPrompt = `${currentPrompt} @${character.name}`.trim()
      setPrompts((current) => ({ ...current, [sceneId]: nextPrompt }))
      savePromptMutate({ sceneId, prompt: nextPrompt })
    },
    [characters.data, scenes, prompts, savePromptMutate]
  )

  // Xoá cạnh nhân vật trên canvas = gỡ @tên khỏi prompt. Cạnh giữa các cảnh
  // (thứ tự/chuyển cảnh) không xoá được qua đây — chỉ cạnh bắt đầu bằng
  // CHARACTER_NODE_PREFIX mới xử lý, còn lại bị bỏ qua nên sẽ tự vẽ lại.
  const onEdgesChange = useCallback(
    (changes: EdgeChange[]) => {
      for (const change of changes) {
        if (change.type !== 'remove') continue
        const edge = allEdges.find((e) => e.id === change.id)
        if (!edge || !edge.source.startsWith(CHARACTER_NODE_PREFIX)) continue

        const characterId = Number(edge.source.slice(CHARACTER_NODE_PREFIX.length))
        const character = characters.data?.find((c) => c.id === characterId)
        const sceneId = Number(edge.target)
        const scene = scenes.find((s) => s.id === sceneId)
        if (!character || !scene) continue

        const currentPrompt = prompts[sceneId] ?? scene.prompt
        const nextPrompt = currentPrompt
          .replace(new RegExp(`@${character.name}\\b`, 'gi'), '')
          .replace(/\s+/g, ' ')
          .trim()
        setPrompts((current) => ({ ...current, [sceneId]: nextPrompt }))
        savePromptMutate({ sceneId, prompt: nextPrompt })
      }
    },
    [allEdges, characters.data, scenes, prompts, savePromptMutate]
  )

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
      if (change.type !== 'position' || !change.position || change.id === OUTPUT_NODE_ID) {
        continue
      }
      if (change.id.startsWith(CHARACTER_NODE_PREFIX)) {
        const characterId = Number(change.id.slice(CHARACTER_NODE_PREFIX.length))
        const position = change.position
        setCharacterPositions((current) => ({ ...current, [characterId]: position }))
        continue
      }
      useFlowStore.getState().moveNode(Number(change.id), change.position.x, change.position.y)
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
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button size='sm' variant='secondary' className='gap-1'>
              <UserPlus className='size-3.5' />
              Thêm nhân vật
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align='start'>
            {(() => {
              const available = (characters.data ?? []).filter(
                (c) => !placedCharacterIds.includes(c.id)
              )
              if (available.length === 0) {
                return (
                  <DropdownMenuItem disabled>
                    {characters.data && characters.data.length > 0
                      ? 'Đã thêm hết bộ ảnh vào canvas'
                      : 'Chưa có bộ ảnh — tạo ở AI Studio'}
                  </DropdownMenuItem>
                )
              }
              return available.map((c) => (
                <DropdownMenuItem key={c.id} onClick={() => addCharacterToCanvas(c.id)}>
                  @{c.name}
                </DropdownMenuItem>
              ))
            })()}
          </DropdownMenuContent>
        </DropdownMenu>
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
        edges={allEdges}
        nodeTypes={nodeTypes}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
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
