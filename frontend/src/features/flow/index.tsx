import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import axios from 'axios'
import { ArrowLeft, Plus, Trash2 } from 'lucide-react'
import { toast } from 'sonner'
import { createProject, deleteProject, getProjects } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { ConfigDrawer } from '@/components/config-drawer'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { ProfileDropdown } from '@/components/profile-dropdown'
import { Search } from '@/components/search'
import { TaskMonitor } from '@/components/task-monitor'
import { ThemeSwitch } from '@/components/theme-switch'
import { ProjectCanvas } from './components/project-canvas'

export function ProjectFlow() {
  const [openProjectId, setOpenProjectId] = useState<number | null>(null)

  return (
    <>
      <Header>
        <Search />
        <div className='ms-auto flex items-center space-x-4'>
          <TaskMonitor />
          <ThemeSwitch />
          <ConfigDrawer />
          <ProfileDropdown />
        </div>
      </Header>

      <Main>
        {openProjectId === null ? (
          <ProjectList onOpen={setOpenProjectId} />
        ) : (
          <>
            <Button
              variant='ghost'
              size='sm'
              className='mb-2 gap-1'
              onClick={() => setOpenProjectId(null)}
            >
              <ArrowLeft className='size-3.5' />
              Danh sách dự án
            </Button>
            <ProjectCanvas projectId={openProjectId} />
          </>
        )}
      </Main>
    </>
  )
}

function ProjectList({ onOpen }: { onOpen: (projectId: number) => void }) {
  const queryClient = useQueryClient()
  const [title, setTitle] = useState('')
  const [script, setScript] = useState('')

  const projects = useQuery({ queryKey: ['projects'], queryFn: getProjects })

  const create = useMutation({
    mutationFn: () => {
      // Mỗi dòng không rỗng là 1 cảnh — dán thẳng kịch bản vào là xong.
      const prompts = script
        .split('\n')
        .map((line) => line.trim())
        .filter(Boolean)
      return createProject(title.trim(), prompts.length > 0 ? prompts : undefined)
    },
    onSuccess: (project) => {
      queryClient.invalidateQueries({ queryKey: ['projects'] })
      setTitle('')
      setScript('')
      toast.success(`Đã tạo "${project.title}" với ${project.scenes.length} cảnh.`)
      onOpen(project.id)
    },
    onError: (error) => {
      const detail = axios.isAxiosError(error)
        ? (error.response?.data as { detail?: string })?.detail
        : null
      toast.error(detail ?? 'Không tạo được dự án.')
    },
  })

  const remove = useMutation({
    mutationFn: deleteProject,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['projects'] })
      toast.success('Đã xoá dự án.')
    },
  })

  return (
    <>
      <div className='mb-4'>
        <h1 className='text-2xl font-bold tracking-tight'>Dự án video</h1>
        <p className='text-muted-foreground'>
          Dựng video nhiều cảnh: mỗi cảnh là một node, đường nối giữa chúng quyết định thứ
          tự phát, nối frame và hiệu ứng chuyển cảnh.
        </p>
      </div>

      <div className='grid gap-4 lg:grid-cols-[380px_1fr]'>
        <Card>
          <CardHeader>
            <CardTitle className='text-base'>Tạo dự án mới</CardTitle>
          </CardHeader>
          <CardContent className='space-y-3'>
            <div className='space-y-1'>
              <Label htmlFor='project-title'>Tên dự án</Label>
              <Input
                id='project-title'
                placeholder='vd Người que học tiết kiệm'
                value={title}
                onChange={(e) => setTitle(e.target.value)}
              />
            </div>

            <div className='space-y-1'>
              <Label htmlFor='project-script'>Kịch bản (mỗi dòng một cảnh)</Label>
              <Textarea
                id='project-script'
                rows={8}
                placeholder={
                  '@nguoique standing alone, neutral expression\n@nguoique sad expression, empty wallet\n@nguoique surprised, pointing at a bar chart'
                }
                value={script}
                onChange={(e) => setScript(e.target.value)}
              />
              <p className='text-muted-foreground text-xs'>
                Để trống cũng được — tạo xong thêm cảnh trực tiếp trên canvas.
              </p>
            </div>

            <Button
              className='gap-1'
              onClick={() => create.mutate()}
              disabled={!title.trim() || create.isPending}
            >
              <Plus className='size-3.5' />
              {create.isPending ? 'Đang tạo...' : 'Tạo dự án'}
            </Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className='text-base'>
              Dự án của tôi ({projects.data?.length ?? 0})
            </CardTitle>
          </CardHeader>
          <CardContent className='space-y-2'>
            {projects.isLoading && (
              <p className='text-muted-foreground text-sm'>Đang tải...</p>
            )}
            {projects.data?.length === 0 && (
              <p className='text-muted-foreground text-sm'>
                Chưa có dự án nào. Tạo một dự án để bắt đầu dựng video nhiều cảnh.
              </p>
            )}
            {projects.data?.map((project) => (
              <div
                key={project.id}
                className='flex items-center gap-2 rounded-md border p-2 text-sm'
              >
                <button
                  type='button'
                  className='min-w-0 flex-1 text-start'
                  onClick={() => onOpen(project.id)}
                >
                  <p className='truncate font-medium'>{project.title}</p>
                  <p className='text-muted-foreground text-xs'>
                    {project.rendered_path ? 'Đã dựng xong' : 'Chưa dựng'} ·{' '}
                    {new Date(project.updated_at).toLocaleString('vi-VN')}
                  </p>
                </button>
                <Button
                  variant='ghost'
                  size='icon'
                  className='size-7'
                  title='Xoá dự án'
                  onClick={() => remove.mutate(project.id)}
                  disabled={remove.isPending}
                >
                  <Trash2 className='size-3.5' />
                </Button>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>
    </>
  )
}
