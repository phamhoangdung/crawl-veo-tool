import { describe, expect, it } from 'vitest'
import {
  autoLayoutLinear,
  edgesFromOrder,
  toSceneOrder,
  validateGraph,
  type GraphEdge,
  type GraphNode,
} from './graph'

function nodes(...ids: string[]): GraphNode[] {
  return ids.map((id) => ({ id, position: { x: 0, y: 0 } }))
}

function edge(source: string, target: string): GraphEdge {
  return { source, target }
}

describe('toSceneOrder', () => {
  it('trả thứ tự theo chuỗi cạnh, không theo thứ tự mảng đầu vào', () => {
    const order = toSceneOrder(nodes('c', 'a', 'b'), [edge('a', 'b'), edge('b', 'c')])

    expect(order).toEqual(['a', 'b', 'c'])
  })

  it('một node đơn lẻ là chuỗi hợp lệ', () => {
    expect(toSceneOrder(nodes('a'), [])).toEqual(['a'])
  })

  it('từ chối chu trình', () => {
    const order = toSceneOrder(nodes('a', 'b'), [edge('a', 'b'), edge('b', 'a')])

    expect(order).toEqual([])
  })

  it('từ chối phân nhánh — renderer chỉ nhận 1 track video', () => {
    const order = toSceneOrder(nodes('a', 'b', 'c'), [edge('a', 'b'), edge('a', 'c')])

    expect(order).toEqual([])
  })

  it('từ chối hai cảnh cùng trỏ vào một cảnh', () => {
    const order = toSceneOrder(nodes('a', 'b', 'c'), [edge('a', 'c'), edge('b', 'c')])

    expect(order).toEqual([])
  })

  it('từ chối graph rời rạc (còn cảnh chưa nối vào chuỗi)', () => {
    const order = toSceneOrder(nodes('a', 'b', 'c'), [edge('a', 'b')])

    expect(order).toEqual([])
  })

  it('từ chối cạnh trỏ tới node không tồn tại', () => {
    expect(toSceneOrder(nodes('a'), [edge('a', 'khong-co')])).toEqual([])
  })
})

describe('validateGraph', () => {
  it('chuỗi tuyến tính là hợp lệ', () => {
    const result = validateGraph(nodes('a', 'b'), [edge('a', 'b')])

    expect(result.ok).toBe(true)
    expect(result.errors).toEqual([])
  })

  it('báo lỗi khi chưa có cảnh nào', () => {
    const result = validateGraph([], [])

    expect(result.ok).toBe(false)
    expect(result.errors[0]).toContain('Chưa có cảnh')
  })

  it('báo rõ khi phân nhánh', () => {
    const result = validateGraph(nodes('a', 'b', 'c'), [edge('a', 'b'), edge('a', 'c')])

    expect(result.ok).toBe(false)
    expect(result.errors.some((e) => e.includes('không phân nhánh'))).toBe(true)
  })

  it('báo rõ khi rời rạc', () => {
    const result = validateGraph(nodes('a', 'b', 'c'), [edge('a', 'b')])

    expect(result.ok).toBe(false)
    expect(result.errors.some((e) => e.includes('một chuỗi liền'))).toBe(true)
  })
})

describe('autoLayoutLinear', () => {
  it('xếp ngang, không chồng nhau', () => {
    const positions = autoLayoutLinear(3)

    expect(positions).toHaveLength(3)
    expect(positions[0].x).toBe(0)
    expect(positions[1].x).toBeGreaterThan(positions[0].x)
    expect(positions.every((p) => p.y === 0)).toBe(true)
  })

  it('không cảnh nào thì không có vị trí nào', () => {
    expect(autoLayoutLinear(0)).toEqual([])
  })
})

describe('edgesFromOrder', () => {
  it('n cảnh cho ra n-1 cạnh nối tiếp', () => {
    expect(edgesFromOrder([10, 20, 30])).toEqual([
      { source: '10', target: '20' },
      { source: '20', target: '30' },
    ])
  })

  it('một cảnh thì không có cạnh nào', () => {
    expect(edgesFromOrder([10])).toEqual([])
  })
})
