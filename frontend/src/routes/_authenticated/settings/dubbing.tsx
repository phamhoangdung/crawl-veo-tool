import { createFileRoute } from '@tanstack/react-router'
import { SettingsDubbing } from '@/features/settings/dubbing'

export const Route = createFileRoute('/_authenticated/settings/dubbing')({
  component: SettingsDubbing,
})
