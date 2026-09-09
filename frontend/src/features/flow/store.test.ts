import { beforeEach, describe, expect, it } from 'vitest'
import { useFlowStore } from './store'

function reset() {
  useFlowStore.getState().setPositions({ 1: { x: 0, y: 0 }, 2: { x: 100, y: 0 } })
}

describe('gộp history theo cử chỉ', () => {
  beforeEach(reset)

  it('cả một cú kéo dài chỉ push đúng 1 entry history', () => {
    const store = useFlowStore.getState()

    store.beginGesture()
    for (let index = 1; index <= 100; index += 1) {
      useFlowStore.getState().moveNode(1, index, index)
    }
    useFlowStore.getState().endGesture()

    // Editor Phase 13 push mỗi pointermove nên chỗ này sẽ là 100 — đó là lỗi
    // khiến undo chỉ lùi được vài pixel.
    expect(useFlowStore.getState().past).toHaveLength(1)
  })

  it('undo trả về đúng vị trí trước khi kéo, không phải bước trung gian', () => {
    useFlowStore.getState().beginGesture()
    useFlowStore.getState().moveNode(1, 50, 50)
    useFlowStore.getState().moveNode(1, 999, 999)
    useFlowStore.getState().endGesture()

    useFlowStore.getState().undo()

    expect(useFlowStore.getState().positions[1]).toEqual({ x: 0, y: 0 })
  })

  it('click (không di chuyển) không tiêu ô history nào', () => {
    useFlowStore.getState().beginGesture()
    useFlowStore.getState().endGesture()

    expect(useFlowStore.getState().past).toHaveLength(0)
  })

  it('hai cú kéo riêng biệt cho hai entry', () => {
    for (const x of [10, 20]) {
      useFlowStore.getState().beginGesture()
      useFlowStore.getState().moveNode(1, x, 0)
      useFlowStore.getState().endGesture()
    }

    expect(useFlowStore.getState().past).toHaveLength(2)
  })

  it('beginGesture lồng nhau không tạo snapshot chồng lấn', () => {
    useFlowStore.getState().beginGesture()
    useFlowStore.getState().moveNode(1, 30, 30)
    useFlowStore.getState().beginGesture() // bị bỏ qua
    useFlowStore.getState().moveNode(1, 60, 60)
    useFlowStore.getState().endGesture()

    useFlowStore.getState().undo()

    expect(useFlowStore.getState().positions[1]).toEqual({ x: 0, y: 0 })
  })
})

describe('undo/redo', () => {
  beforeEach(reset)

  it('redo lặp lại thao tác vừa undo', () => {
    useFlowStore.getState().beginGesture()
    useFlowStore.getState().moveNode(2, 500, 500)
    useFlowStore.getState().endGesture()

    useFlowStore.getState().undo()
    useFlowStore.getState().redo()

    expect(useFlowStore.getState().positions[2]).toEqual({ x: 500, y: 500 })
  })

  it('thao tác mới xoá nhánh redo', () => {
    useFlowStore.getState().beginGesture()
    useFlowStore.getState().moveNode(1, 10, 10)
    useFlowStore.getState().endGesture()
    useFlowStore.getState().undo()

    useFlowStore.getState().beginGesture()
    useFlowStore.getState().moveNode(1, 70, 70)
    useFlowStore.getState().endGesture()

    expect(useFlowStore.getState().future).toHaveLength(0)
  })

  it('undo khi chưa có gì thì không lỗi', () => {
    useFlowStore.getState().undo()

    expect(useFlowStore.getState().positions[1]).toEqual({ x: 0, y: 0 })
  })
})

describe('cờ dirty', () => {
  beforeEach(reset)

  it('nạp từ server không coi là có thay đổi cần lưu', () => {
    expect(useFlowStore.getState().dirty).toBe(false)
  })

  it('kéo node đánh dấu cần lưu, markSaved xoá cờ', () => {
    useFlowStore.getState().moveNode(1, 5, 5)
    expect(useFlowStore.getState().dirty).toBe(true)

    useFlowStore.getState().markSaved()

    expect(useFlowStore.getState().dirty).toBe(false)
  })
})
