/** Pure graph math for the video-building canvas — split out of the component so it can be tested,
 *  the same way `features/editor/layout.ts` does.
 *
 *  Core constraint: the scene chain must be **linear**. `ffmpeg.render_timeline`
 *  (backend, app/adapters/ffmpeg.py) accepts exactly 1 video track, so a branching
 *  graph would build something the renderer cannot express.
 */

export const SCENE_NODE_WIDTH = 260
export const SCENE_NODE_GAP = 60
export const CHARACTER_NODE_WIDTH = 180
/** Id prefix of character nodes on the canvas — distinguishes them from scene ids (both numbers,
 *  from different tables) without stuffing 2 meanings into 1 field like a negative id. */
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

/** The playback order derived from the edges. Returns [] if the graph is invalid. */
export function toSceneOrder(nodes: GraphNode[], edges: GraphEdge[]): string[] {
  if (nodes.length === 0) return []

  const incoming = new Map<string, number>()
  const nextOf = new Map<string, string>()
  for (const node of nodes) incoming.set(node.id, 0)

  for (const edge of edges) {
    if (!incoming.has(edge.source) || !incoming.has(edge.target)) return []
    // An outgoing edge already exists from source, or an incoming edge to target = branching, not linear.
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
    if (seen.has(current)) return [] // cycle
    seen.add(current)
    order.push(current)
    current = nextOf.get(current)
  }

  // A node not connected into the chain = a disconnected graph.
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

/** Default position when the canvas is not saved yet: laid out horizontally in a row. */
export function autoLayoutLinear(count: number): { x: number; y: number }[] {
  return Array.from({ length: count }, (_, index) => ({
    x: index * (SCENE_NODE_WIDTH + SCENE_NODE_GAP),
    y: 0,
  }))
}

/** Edges derived from the scene order — the source of truth of the order is `order_index` in the
 *  backend, the canvas only redraws it for readability. */
export function edgesFromOrder(sceneIds: number[]): GraphEdge[] {
  return sceneIds.slice(0, -1).map((id, index) => ({
    source: String(id),
    target: String(sceneIds[index + 1]),
  }))
}

const MENTION_PATTERN = /@([a-z0-9_]+)/g

/** Extract the @names mentioned in the prompt, deduplicated, case
 *  insensitive — the same convention as `features/ai-studio/components/keyframe-step.tsx`. */
export function parseMentions(prompt: string): string[] {
  const matches = prompt.toLowerCase().match(MENTION_PATTERN) ?? []
  return Array.from(new Set(matches.map((m) => m.slice(1))))
}

/** Character → scene edges, derived from the @mention in the prompt — not stored as
 *  separate state to avoid 2 sources of truth (canvas vs prompt text). Connecting then
 *  removing this edge is only a visual way to insert/remove @name in the prompt.
 *  `characters` should only be the characters currently present on the canvas, not
 *  the whole reference library — a mention not dragged onto the canvas gets no edge. */
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
