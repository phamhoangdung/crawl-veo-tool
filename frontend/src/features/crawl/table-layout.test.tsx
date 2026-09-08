import { render } from 'vitest-browser-react'
import { describe, expect, it } from 'vitest'
import '@/styles/index.css'
import { CoverImage } from '@/components/cover-image'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'

// Tiêu đề tiếng Trung dài thật như Bilibili trả về — đây là thứ làm bảng tràn
// ngang và bóp cột ảnh trước khi sửa.
const LONG_TITLE =
  '一看就懂！最完整的匹克球规则详解，从零开始学习匹克球运动的所有基础知识和进阶技巧，新手必看的完整教程'

/** Dựng đúng cấu trúc bảng của trang Crawl để đo layout thật. */
function CrawlTable({ rows }: { rows: number }) {
  return (
    <div style={{ width: 900 }}>
      <Table className='table-fixed'>
        <TableHeader>
          <TableRow>
            <TableHead className='w-[132px]'>Ảnh</TableHead>
            <TableHead className='min-w-0'>Tiêu đề</TableHead>
            <TableHead className='w-32'>Tác giả</TableHead>
            <TableHead className='w-24'>Thời lượng</TableHead>
            <TableHead className='w-28'>Trạng thái</TableHead>
            <TableHead className='w-36'>Thao tác</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {Array.from({ length: rows }, (_, i) => (
            <TableRow key={i}>
              <TableCell>
                <CoverImage src={null} className='w-28 rounded' />
              </TableCell>
              <TableCell className='min-w-0'>
                <a title={LONG_TITLE} className='block truncate'>
                  {LONG_TITLE}
                </a>
              </TableCell>
              <TableCell className='truncate'>匹克球图书馆频道名称很长</TableCell>
              <TableCell>50:18</TableCell>
              <TableCell>queued</TableCell>
              <TableCell>Tải video</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}

describe('Bảng Crawl — layout', () => {
  it('ảnh thumb giữ nguyên kích thước dù tiêu đề rất dài', async () => {
    await render(<CrawlTable rows={8} />)
    const imgs = [...document.querySelectorAll('tbody td:first-child > div')]

    expect(imgs.length).toBe(8)
    const widths = imgs.map((el) => el.getBoundingClientRect().width)
    // Mọi ảnh cùng bề rộng và đúng 112px (w-28) — trước đây cột bị bóp lại.
    expect(new Set(widths).size).toBe(1)
    expect(widths[0]).toBe(112)
  })

  it('ảnh không nhỏ đi khi load thêm nhiều dòng', async () => {
    await render(<CrawlTable rows={3} />)
    const few = document.querySelector('tbody td:first-child > div')!.getBoundingClientRect().width
    document.body.innerHTML = ''

    await render(<CrawlTable rows={40} />)
    const many = document.querySelector('tbody td:first-child > div')!.getBoundingClientRect().width

    // Đây là hiện tượng "load thêm thì lại nhỏ nữa".
    expect(many).toBe(few)
  })

  it('tiêu đề dài bị cắt bằng … chứ không làm bảng tràn ngang', async () => {
    await render(<CrawlTable rows={8} />)
    const table = document.querySelector('table')!
    const link = document.querySelector('table a')!

    expect(getComputedStyle(link).textOverflow).toBe('ellipsis')
    // Chữ thật dài hơn khung hiển thị -> đúng là đang bị cắt.
    expect(link.scrollWidth).toBeGreaterThan(link.clientWidth)
    // Bảng không rộng hơn khung chứa 900px.
    expect(table.getBoundingClientRect().width).toBeLessThanOrEqual(900)
  })

  it('cột Thao tác không bị đẩy ra ngoài khung', async () => {
    await render(<CrawlTable rows={8} />)
    const container = document.querySelector('div[style]')!
    const lastCell = [...document.querySelectorAll('tbody tr:first-child td')].at(-1)!

    const right = lastCell.getBoundingClientRect().right
    // Trước khi sửa, cột "Thao tác" bị cắt mất một phần bên phải.
    expect(right).toBeLessThanOrEqual(container.getBoundingClientRect().right + 1)
  })
})
