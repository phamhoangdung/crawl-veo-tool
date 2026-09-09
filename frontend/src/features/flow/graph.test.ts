import { describe, expect, it } from 'vitest'
import {
  autoLayoutLinear,
  characterEdgesFromMentions,
  edgesFromOrder,
  parseMentions,
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

describe('parseMentions', () => {
  it('rút @tên, khử trùng, không phân biệt hoa thường', () => {
    expect(parseMentions('@Hero gặp @npc_ba và lại nhắc @hero')).toEqual(['hero', 'npc_ba'])
  })

  it('không có mention thì mảng rỗng', () => {
    expect(parseMentions('cảnh rừng, không ai nói gì')).toEqual([])
  })
})

describe('characterEdgesFromMentions', () => {
  it('tạo cạnh nhân vật → cảnh khi prompt nhắc @tên khớp nhân vật đang trên canvas', () => {
    const edges = characterEdgesFromMentions(
      [
        { id: 1, prompt: '@hero bước vào quán' },
        { id: 2, prompt: 'cảnh trống, không ai' },
        { id: 3, prompt: '@hero và @villain đối đầu' },
      ],
      [
        { id: 10, name: 'hero' },
        { id: 20, name: 'villain' },
      ]
    )

    expect(edges).toEqual([
      { source: 'char-10', target: '1' },
      { source: 'char-10', target: '3' },
      { source: 'char-20', target: '3' },
    ])
  })

  it('bỏ qua mention không khớp nhân vật nào đang có trên canvas', () => {
    const edges = characterEdgesFromMentions(
      [{ id: 1, prompt: '@unknown xuất hiện' }],
      [{ id: 10, name: 'hero' }]
    )

    expect(edges).toEqual([])
  })
})
