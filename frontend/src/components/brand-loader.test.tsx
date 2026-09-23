import '@/styles/index.css'
import { describe, expect, it } from 'vitest'
import { render } from 'vitest-browser-react'
import { BrandLoader, LoadingOverlay } from './brand-loader'

describe('BrandLoader', () => {
  it('có % → progressbar mang giá trị thật và hiện số %', async () => {
    const screen = await render(
      <BrandLoader percent={42.4} label='Đang xử lý' />
    )
    await expect.element(screen.getByText('42%')).toBeVisible()
    await expect.element(screen.getByText('Đang xử lý')).toBeVisible()
    await expect
      .element(screen.getByRole('progressbar'))
      .toHaveAttribute('aria-valuenow', '42.4')
  })

  it('kẹp % ngoài khoảng 0-100', async () => {
    const screen = await render(<BrandLoader percent={250} />)
    await expect.element(screen.getByText('100%')).toBeVisible()
  })

  it('không có % → thanh vô định, không hiện dấu %', async () => {
    const screen = await render(<BrandLoader />)
    await expect.element(screen.getByText('Đang tải...')).toBeVisible()
    expect(screen.getByText('%').query()).toBeNull()
  })

  it('LoadingOverlay đóng thì không render gì', async () => {
    const screen = await render(<LoadingOverlay open={false} label='Đợi' />)
    expect(screen.getByText('Đợi').query()).toBeNull()
  })
})
