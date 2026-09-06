import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getDownloadUrl, getLibrary, getZipDownloadUrl } from '@/lib/api'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { ConfigDrawer } from '@/components/config-drawer'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { ProfileDropdown } from '@/components/profile-dropdown'
import { Search } from '@/components/search'
import { ThemeSwitch } from '@/components/theme-switch'

export function Library() {
  const { data: items } = useQuery({ queryKey: ['library'], queryFn: getLibrary })
  const [selected, setSelected] = useState<number[]>([])

  const toggle = (id: number) =>
    setSelected((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]))

  return (
    <>
      <Header>
        <Search />
        <div className='ms-auto flex items-center space-x-4'>
          <ThemeSwitch />
          <ConfigDrawer />
          <ProfileDropdown />
        </div>
      </Header>

      <Main>
        <div className='mb-4 flex items-center justify-between'>
          <div>
            <h1 className='text-2xl font-bold tracking-tight'>Library</h1>
            <p className='text-muted-foreground'>Video đã xử lý — tải lẻ hoặc chọn nhiều để tải zip.</p>
          </div>
          {selected.length > 0 && (
            <a href={getZipDownloadUrl(selected, 'dubbed')}>
              <Button>Tải zip ({selected.length})</Button>
            </a>
          )}
        </div>

        <Card>
          <CardHeader>
            <CardTitle>Danh sách video</CardTitle>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead />
                  <TableHead>Tiêu đề</TableHead>
                  <TableHead>Nền tảng</TableHead>
                  <TableHead>Trạng thái</TableHead>
                  <TableHead>Tải về</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {items?.map((item) => (
                  <TableRow key={item.id}>
                    <TableCell>
                      <Checkbox
                        checked={selected.includes(item.id)}
                        onCheckedChange={() => toggle(item.id)}
                      />
                    </TableCell>
                    <TableCell className='max-w-xs truncate'>{item.title}</TableCell>
                    <TableCell>{item.platform}</TableCell>
                    <TableCell>
                      <Badge variant='outline'>{item.status}</Badge>
                    </TableCell>
                    <TableCell className='flex gap-2'>
                      {item.has_dubbed && (
                        <a href={getDownloadUrl(item.id, 'dubbed')}>
                          <Button size='sm' variant='outline'>
                            Đã lồng tiếng
                          </Button>
                        </a>
                      )}
                      {item.has_burned && (
                        <a href={getDownloadUrl(item.id, 'burned')}>
                          <Button size='sm' variant='outline'>
                            Có phụ đề
                          </Button>
                        </a>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      </Main>
    </>
  )
}
