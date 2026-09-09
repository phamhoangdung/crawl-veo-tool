/** Toán graph thuần cho canvas dựng video — tách khỏi component để test được,
 *  cùng cách `features/editor/layout.ts` làm.
 *
 *  Ràng buộc cốt lõi: chuỗi cảnh phải **tuyến tính**. `ffmpeg.render_timeline`
 *  (backend, app/adapters/ffmpeg.py) nhận đúng 1 track video, nên graph phân
 *  nhánh sẽ dựng được thứ mà renderer không diễn đạt nổi.
 */

export const SCENE_NODE_WIDTH = 260
export const SCENE_NODE_GAP = 60
export const CHARACTER_NODE_WIDTH = 180
/** Tiền tố id node nhân vật trên canvas — phân biệt với id cảnh (cùng là số,
 *  khác bảng) mà không phải nhét 2 ý nghĩa vào 1 field như id âm. */
export const CHARACTER_NODE_PREFIX = 'char-'

export interface GraphNode {
  id: string
  position: { x: number; y: number }
}

export interface GraphEdge {
  source: string
  target: string
}

export interface GraphValidation {
  ok: boolean
  errors: string[]
}

/** Thứ tự phát suy ra từ các cạnh. Trả [] nếu graph không hợp lệ. */
export function toSceneOrder(nodes: GraphNode[], edges: GraphEdge[]): string[] {
  if (nodes.length === 0) return []

  const incoming = new Map<string, number>()
  const nextOf = new Map<string, string>()
  for (const node of nodes) incoming.set(node.id, 0)

  for (const edge of edges) {
    if (!incoming.has(edge.source) || !incoming.has(edge.target)) return []
    // Đã có cạnh ra từ source hoặc cạnh vào target = phân nhánh, không tuyến tính.
    if (nextOf.has(edge.source)) return []
    incoming.set(edge.target, (incoming.get(edge.target) ?? 0) + 1)
    if ((incoming.get(edge.target) ?? 0) > 1) return []
    nextOf.set(edge.source, edge.target)
  }

  const starts = nodes.filter((n) => (incoming.get(n.id) ?? 0) === 0)
  if (starts.length !== 1) return []

  const order: string[] = []
  const seen = new Set<string>()
  let current: string | undefined = starts[0].id
  while (current !== undefined) {
    if (seen.has(current)) return [] // chu trình
    seen.add(current)
    order.push(current)
    current = nextOf.get(current)
  }

  // Còn node chưa nối vào chuỗi = graph rời rạc.
  return order.length === nodes.length ? order : []
}

export function validateGraph(nodes: GraphNode[], edges: GraphEdge[]): GraphValidation {
  const errors: string[] = []

  if (nodes.length === 0) {
    return { ok: false, errors: ['Chưa có cảnh nào — thêm cảnh trước khi dựng.'] }
  }

  const outCount = new Map<string, number>()
  const inCount = new Map<string, number>()
  for (const edge of edges) {
    outCount.set(edge.source, (outCount.get(edge.source) ?? 0) + 1)
    inCount.set(edge.target, (inCount.get(edge.target) ?? 0) + 1)
  }

  if ([...outCount.values()].some((count) => count > 1)) {
    errors.push('Một cảnh chỉ được nối tới một cảnh kế tiếp (không phân nhánh).')
  }
  if ([...inCount.values()].some((count) => count > 1)) {
    errors.push('Một cảnh chỉ được nhận một cảnh phía trước.')
  }

  if (nodes.length > 1 && toSceneOrder(nodes, edges).length === 0) {
    errors.push('Các cảnh phải nối thành một chuỗi liền, không vòng lặp và không rời rạc.')
  }

  return { ok: errors.length === 0, errors }
}

/** Vị trí mặc định khi chưa lưu canvas: xếp ngang thành hàng. */
export function autoLayoutLinear(count: number): { x: number; y: number }[] {
  return Array.from({ length: count }, (_, index) => ({
    x: index * (SCENE_NODE_WIDTH + SCENE_NODE_GAP),
    y: 0,
  }))
}

/** Cạnh suy ra từ thứ tự cảnh — nguồn sự thật của thứ tự là `order_index` ở
 *  backend, canvas chỉ vẽ lại cho dễ nhìn. */
export function edgesFromOrder(sceneIds: number[]): GraphEdge[] {
  return sceneIds.slice(0, -1).map((id, index) => ({
    source: String(id),
    target: String(sceneIds[index + 1]),
  }))
}

const MENTION_PATTERN = /@([a-z0-9_]+)/g

/** Rút các @tên được nhắc trong prompt, khử trùng, không phân biệt hoa
 *  thường — cùng quy ước với `features/ai-studio/components/keyframe-step.tsx`. */
export function parseMentions(prompt: string): string[] {
  const matches = prompt.toLowerCase().match(MENTION_PATTERN) ?? []
  return Array.from(new Set(matches.map((m) => m.slice(1))))
}

/** Cạnh nhân vật → cảnh, suy ra từ @mention trong prompt — không lưu thành
 *  trạng thái riêng để tránh 2 nguồn sự thật (canvas vs text prompt). Nối rồi
 *  tháo cạnh này chỉ là cách trực quan để chèn/xoá @tên trong prompt.
 *  `characters` chỉ nên là các nhân vật đang có mặt trên canvas, không phải
 *  toàn bộ kho tham chiếu — mention chưa kéo ra canvas thì không vẽ cạnh. */
export function characterEdgesFromMentions(
  scenes: { id: number; prompt: string }[],
  characters: { id: number; name: string }[]
): GraphEdge[] {
  const characterIdByName = new Map(characters.map((c) => [c.name, c.id]))
  const edges: GraphEdge[] = []
  for (const scene of scenes) {
    for (const name of parseMentions(scene.prompt)) {
      const characterId = characterIdByName.get(name)
      if (characterId !== undefined) {
        edges.push({ source: `${CHARACTER_NODE_PREFIX}${characterId}`, target: String(scene.id) })
      }
    }
  }
  return edges
}
