import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getGenerationBudget, getGenerationMode } from '@/lib/api'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { ConfigDrawer } from '@/components/config-drawer'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { ProfileDropdown } from '@/components/profile-dropdown'
import { Search } from '@/components/search'
import { TaskMonitor } from '@/components/task-monitor'
import { ThemeSwitch } from '@/components/theme-switch'
import { CharacterReferencePanel } from './components/character-reference-panel'
import { GenerationSettingsPanel } from './components/generation-settings-panel'
import { KeyframeStep } from './components/keyframe-step'
import { SessionHistory } from './components/session-history'
import { VideoStep } from './components/video-step'
import { type StudioSettings } from './types'

const DEFAULT_SETTINGS: StudioSettings = {
  imageModel: 'nano-banana',
  videoModel: 'kling-3.0',
  variantCount: 4,
  outputPrefix: '',
}

export function AiStudio() {
  const [settings, setSettings] = useState<StudioSettings>(DEFAULT_SETTINGS)
  const [selectedKeyframeId, setSelectedKeyframeId] = useState<number | null>(null)

  const mode = useQuery({ queryKey: ['ai-studio', 'mode'], queryFn: getGenerationMode })
  const budget = useQuery({
    queryKey: ['ai-studio', 'budget'],
    queryFn: getGenerationBudget,
  })

  const overBudget =
    budget.data != null && budget.data.remaining_usd <= 0 && budget.data.monthly_budget_usd > 0

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
        <div className='mb-4 flex flex-wrap items-start justify-between gap-2'>
          <div>
            <h1 className='text-2xl font-bold tracking-tight'>AI Studio</h1>
            <p className='text-muted-foreground'>
              Tạo video mới từ đầu: ảnh nhân vật mẫu → ảnh keyframe → clip. Cảnh không cần
              chuyển động thật thì dùng ảnh tĩnh + chuyển động camera (miễn phí).
            </p>
          </div>
          {budget.data && (
            <Badge variant={overBudget ? 'destructive' : 'outline'} className='mt-1'>
              Tháng này: ${budget.data.spent_this_month_usd.toFixed(2)} / $
              {budget.data.monthly_budget_usd.toFixed(2)}
            </Badge>
          )}
        </div>

        {mode.data?.is_fake && (
          <Alert className='mb-4'>
            <AlertTitle>Đang ở chế độ thử nghiệm</AlertTitle>
            <AlertDescription>
              <span>
                Ảnh và video sinh ra là file giả (ffmpeg), không gọi API thật và không tốn
                phí. Đặt <code className='font-mono'>FALAI_MODE=real</code> trong{' '}
                <code className='font-mono'>backend/.env</code> khi muốn dùng provider thật.
              </span>
            </AlertDescription>
          </Alert>
        )}

        {overBudget && (
          <Alert variant='destructive' className='mb-4'>
            <AlertTitle>Đã dùng hết hạn mức tháng</AlertTitle>
            <AlertDescription>
              Mọi lần sinh tốn phí sẽ bị chặn. Tăng <code>FALAI_MONTHLY_BUDGET_USD</code> hoặc
              chờ sang tháng. Đường ảnh tĩnh + chuyển động camera vẫn dùng được (miễn phí).
            </AlertDescription>
          </Alert>
        )}

        <div className='grid gap-4 lg:grid-cols-[280px_1fr]'>
          <div className='space-y-4'>
            <CharacterReferencePanel />
            <GenerationSettingsPanel settings={settings} onChange={setSettings} />
          </div>

          <div className='space-y-4'>
            <KeyframeStep
              settings={settings}
              selectedKeyframeId={selectedKeyframeId}
              onSelectKeyframe={setSelectedKeyframeId}
            />
            <VideoStep settings={settings} selectedKeyframeId={selectedKeyframeId} />
            <SessionHistory />
          </div>
        </div>
      </Main>
    </>
  )
}
