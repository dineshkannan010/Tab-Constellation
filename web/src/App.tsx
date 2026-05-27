import { useEffect, useRef, useState, useCallback } from 'react'
import * as THREE from 'three'

const API = ''

// ── Types ──────────────────────────────────────────────────────
type Node = {
  node_id: string; title: string; domain: string; cluster: string
  focus_score: number; is_distraction: boolean; is_escape_node: boolean
  days_since_visit: number; session_id: string; depth: number
  url: string; visit_count: number; time_spent: number; meta_description?: string
}
type ChainNode = {
  title: string; domain: string; cluster: string; depth: number
  is_distraction: boolean; time_spent: number; url: string
}
type RabbitHole = {
  session_id: string; max_depth: number; total_time: number
  node_count: number; has_distraction: boolean
  origin_cluster: string; exit_cluster: string; chain: ChainNode[]
}
type DistractionSummary = {
  total: number; time_lost: number
  by_domain: { domain: string; visits: number; time_spent: number }[]
  by_cluster: { cluster: string; count: number; time_spent: number }[]
}
type FocusSummary = {
  avg_focus: number; total_time: number; focus_time: number
  distraction_time: number; total_nodes: number; distraction_nodes: number
}

// ── Colors ─────────────────────────────────────────────────────
const CLUSTER_COLORS: Record<string, number> = {
  'research': 0x60a5fa, 'work': 0x34d399, 'entertainment': 0xf87171,
  'shopping': 0xf97316, 'social': 0xfbbf24, 'news': 0xfda4af,
  'finance': 0xfcd34d, 'health': 0x86efac, 'travel': 0x22d3ee,
  'creative': 0xa78bfa, 'reference': 0x94a3b8, 'communication': 0xe879f9,
  'ai-research': 0x60a5fa, 'programming': 0x34d399, 'general': 0x94a3b8,
}
const cc = (c: string) => CLUSTER_COLORS[c] ?? 0x94a3b8
const hex = (n: number) => `#${n.toString(16).padStart(6, '0')}`
const fmt = (s: number) => s < 60 ? `${s}s` : s < 3600 ? `${Math.round(s/60)}m` : `${(s/3600).toFixed(1)}h`

type Panel = 'none' | 'rabbit' | 'distraction' | 'focus'

// ── CSS injected once ──────────────────────────────────────────
const GLOBAL_CSS = `
  @import url('https://fonts.googleapis.com/css2?family=Space+Mono:ital,wght@0,400;0,700;1,400&family=Syne:wght@400;600;700;800&display=swap');
  * { box-sizing: border-box; margin: 0; padding: 0; }
  html { scroll-behavior: smooth; scroll-snap-type: y mandatory; }
  body { background: #020817; font-family: 'Syne', sans-serif; overflow-x: hidden; }
  ::-webkit-scrollbar { width: 3px; }
  ::-webkit-scrollbar-track { background: #020817; }
  ::-webkit-scrollbar-thumb { background: #1e3a5f; border-radius: 99px; }

  @keyframes pulse-ring {
    0% { transform: scale(1); opacity: 1; }
    100% { transform: scale(2.5); opacity: 0; }
  }
  @keyframes float {
    0%, 100% { transform: translateY(0px); }
    50% { transform: translateY(-12px); }
  }
  @keyframes spin-slow {
    from { transform: rotate(0deg); }
    to { transform: rotate(360deg); }
  }
  @keyframes scroll-bounce {
    0%, 100% { transform: translateY(0) translateX(-50%); opacity: 0.4; }
    50% { transform: translateY(8px) translateX(-50%); opacity: 1; }
  }
  @keyframes wormhole-spin {
    from { transform: rotateY(0deg); }
    to { transform: rotateY(360deg); }
  }
  @keyframes crash-shake {
    0%, 100% { transform: translateX(0); }
    20% { transform: translateX(-4px) rotate(-1deg); }
    40% { transform: translateX(4px) rotate(1deg); }
    60% { transform: translateX(-2px); }
    80% { transform: translateX(2px); }
  }
  @keyframes suck-in {
    0% { transform: scale(1) rotate(0deg); opacity: 1; }
    100% { transform: scale(0) rotate(720deg); opacity: 0; }
  }
  @keyframes dead-pulse {
    0%, 100% { opacity: 0.15; transform: scale(1); }
    50% { opacity: 0.4; transform: scale(1.05); }
  }
  @keyframes gauge-fill {
    from { stroke-dashoffset: 220; }
    to { stroke-dashoffset: var(--target); }
  }
  @keyframes fade-up {
    from { opacity: 0; transform: translateY(20px); }
    to { opacity: 1; transform: translateY(0); }
  }
  @keyframes star-twinkle {
    0%, 100% { opacity: 0.3; }
    50% { opacity: 1; }
  }
  .section {
    height: 100vh; width: 100vw; position: relative;
    scroll-snap-align: start; overflow: hidden;
    display: flex; align-items: center; justify-content: center;
  }
  .mono { font-family: 'Space Mono', monospace; }
  .fade-up { animation: fade-up 0.8s ease forwards; }
  .floating { animation: float 4s ease-in-out infinite; }

  #scroll-container { width: 100vw; }
  .section { width: 100vw !important; }
`

// ── Starfield background (reusable canvas) ─────────────────────
function StarField({ id }: { id: string }) {
  const ref = useRef<HTMLCanvasElement>(null)
  useEffect(() => {
    const c = ref.current; if (!c) return
    const ctx = c.getContext('2d')!
    c.width = window.innerWidth; c.height = window.innerHeight
    const stars = Array.from({ length: 200 }, () => ({
      x: Math.random() * c.width, y: Math.random() * c.height,
      r: Math.random() * 1.5, t: Math.random() * Math.PI * 2,
    }))
    let raf: number
    function draw() {
      ctx.clearRect(0, 0, c.width, c.height)
      stars.forEach(s => {
        s.t += 0.01
        ctx.beginPath()
        ctx.arc(s.x, s.y, s.r, 0, Math.PI * 2)
        ctx.fillStyle = `rgba(148,163,184,${0.2 + Math.sin(s.t) * 0.3})`
        ctx.fill()
      })
      raf = requestAnimationFrame(draw)
    }
    draw()
    return () => cancelAnimationFrame(raf)
  }, [id])
  return <canvas ref={ref} style={{ position: 'absolute', inset: 0, width: '100%', height: '100%' }} />
}

// ── Main App ───────────────────────────────────────────────────
export default function App() {
  const mountRef    = useRef<HTMLDivElement>(null)
  const meshesRef   = useRef<THREE.Mesh[]>([])
  const nodeMapRef  = useRef<Map<THREE.Mesh, Node>>(new Map())

  const [allNodes,      setAllNodes]      = useState<Node[]>([])
  const [nodes,         setNodes]         = useState<Node[]>([])
  const [hovered,       setHovered]       = useState<Node | null>(null)
  const [selected,      setSelected]      = useState<Node | null>(null)
  const [loading,       setLoading]       = useState(true)
  const [activeCluster, setActiveCluster] = useState<string | null>(null)
  const [maxDays,       setMaxDays]       = useState(30)
  const [searchQuery,   setSearchQuery]   = useState('')
  const [searching,     setSearching]     = useState(false)
  const [highlightUrls, setHighlightUrls] = useState<Set<string>>(new Set())
  const [panel,         setPanel]         = useState<Panel>('none')
  const [rabbitHoles,   setRabbitHoles]   = useState<RabbitHole[]>([])
  const [distraction,   setDistraction]   = useState<DistractionSummary | null>(null)
  const [focusSummary,  setFocusSummary]  = useState<FocusSummary | null>(null)
  const [scrollY,       setScrollY]       = useState(0)

  // Inject CSS
  useEffect(() => {
    const el = document.createElement('style')
    el.textContent = GLOBAL_CSS
    document.head.appendChild(el)
    return () => document.head.removeChild(el)
  }, [])

  // Track scroll
  useEffect(() => {
    const el = document.getElementById('scroll-container')
    if (!el) return
    const onScroll = () => setScrollY(el.scrollTop)
    el.addEventListener('scroll', onScroll)
    return () => el.removeEventListener('scroll', onScroll)
  }, [])

  // Fetch nodes
  useEffect(() => {
    fetch(`${API}/api/v1/nodes/all?limit=200`)
      .then(r => r.json())
      .then(d => { setAllNodes(d.nodes ?? []); setLoading(false) })
      .catch(() => setLoading(false))
  }, [])

  // Filter
  useEffect(() => {
    let f = allNodes
    if (activeCluster) f = f.filter(n => n.cluster === activeCluster)
    f = f.filter(n => n.days_since_visit <= maxDays)
    setNodes(f)
  }, [allNodes, activeCluster, maxDays])

  // Fetch insights
  useEffect(() => {
    if (panel === 'rabbit' && rabbitHoles.length === 0)
      fetch(`${API}/api/v1/insights/rabbit-holes`).then(r => r.json()).then(d => setRabbitHoles(d.rabbit_holes ?? []))
    if (panel === 'distraction' && !distraction)
      fetch(`${API}/api/v1/insights/distraction-summary`).then(r => r.json()).then(d => setDistraction(d))
    if (panel === 'focus' && !focusSummary)
      fetch(`${API}/api/v1/insights/focus-summary`).then(r => r.json()).then(d => setFocusSummary(d))
  }, [panel])

  // Preload all insights for scroll sections
  useEffect(() => {
    if (allNodes.length === 0) return
    fetch(`${API}/api/v1/insights/rabbit-holes`).then(r => r.json()).then(d => setRabbitHoles(d.rabbit_holes ?? []))
    fetch(`${API}/api/v1/insights/distraction-summary`).then(r => r.json()).then(d => setDistraction(d))
    fetch(`${API}/api/v1/insights/focus-summary`).then(r => r.json()).then(d => setFocusSummary(d))
  }, [allNodes.length])

  // Highlight effect
  useEffect(() => {
    meshesRef.current.forEach(mesh => {
      const node = nodeMapRef.current.get(mesh)
      if (!node) return
      const mat = mesh.material as THREE.MeshStandardMaterial
      if (highlightUrls.size === 0) {
        mat.emissiveIntensity = node.is_escape_node ? 1.0 : 0.3
        mat.opacity = node.days_since_visit > 21 ? 0.2 : 1.0
        mat.color.setHex(cc(node.cluster))
      } else if (highlightUrls.has(node.url)) {
        mat.emissiveIntensity = 2.5
        mat.opacity = 1.0
        mat.color.setHex(0xffffff)
      } else {
        mat.emissiveIntensity = 0.05
        mat.opacity = 0.08
      }
    })
  }, [highlightUrls])

  // Semantic search
  const runSearch = useCallback(async (query: string) => {
    if (!query.trim()) { setHighlightUrls(new Set()); return }
    setSearching(true)
    try {
      const res = await fetch(`${API}/api/v1/search/semantic`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query, top_k: 15, min_score: 0.2 }),
      })
      const data = await res.json()
      setHighlightUrls(new Set((data as { score: number; node: Node }[]).map(r => r.node.url)))
    } catch (e) { console.error(e) }
    setSearching(false)
  }, [])

  const clusters = Array.from(new Set(allNodes.map(n => n.cluster))).sort()

  // ── Three.js scene ──────────────────────────────────────────
  useEffect(() => {
    const el = mountRef.current
    if (!el || nodes.length === 0) return
    const W = el.clientWidth, H = el.clientHeight

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true })
    renderer.setSize(W, H)
    renderer.setPixelRatio(window.devicePixelRatio)
    renderer.setClearColor(0x000000, 0)
    el.appendChild(renderer.domElement)

    const scene = new THREE.Scene()
    const camera = new THREE.PerspectiveCamera(60, W / H, 0.1, 1000)
    camera.position.set(0, 0, 80)

    scene.add(new THREE.AmbientLight(0xffffff, 0.5))
    const pt = new THREE.PointLight(0x60a5fa, 3, 300)
    pt.position.set(0, 50, 50)
    scene.add(pt)
    const pt2 = new THREE.PointLight(0xf87171, 2, 200)
    pt2.position.set(-50, -30, 30)
    scene.add(pt2)

    // Starfield particles
    const starGeo = new THREE.BufferGeometry()
    const starVerts = []
    for (let i = 0; i < 2000; i++) {
      starVerts.push(
        (Math.random() - 0.5) * 400,
        (Math.random() - 0.5) * 400,
        (Math.random() - 0.5) * 400,
      )
    }
    starGeo.setAttribute('position', new THREE.Float32BufferAttribute(starVerts, 3))
    const starMat = new THREE.PointsMaterial({ color: 0x334155, size: 0.3 })
    scene.add(new THREE.Points(starGeo, starMat))

    const meshes: THREE.Mesh[] = []
    const nodeMap = new Map<THREE.Mesh, Node>()
    meshesRef.current = meshes
    nodeMapRef.current = nodeMap

    nodes.forEach((node, i) => {
      const phi   = Math.acos(-1 + (2 * i) / nodes.length)
      const theta = Math.sqrt(nodes.length * Math.PI) * phi
      const r     = 28 + node.depth * 3.5
      const x = r * Math.sin(phi) * Math.cos(theta)
      const y = r * Math.sin(phi) * Math.sin(theta)
      const z = r * Math.cos(phi)

      const size = 0.35 + node.focus_score * 0.9 + Math.min((node.time_spent ?? 0) / 500, 0.7)
      const color = cc(node.cluster)

      // Glow ring for distractions
      if (node.is_distraction) {
        const ringGeo = new THREE.RingGeometry(size * 1.4, size * 1.7, 32)
        const ringMat = new THREE.MeshBasicMaterial({
          color: 0xf87171, transparent: true, opacity: 0.15, side: THREE.DoubleSide
        })
        const ring = new THREE.Mesh(ringGeo, ringMat)
        ring.position.set(x, y, z)
        ring.lookAt(camera.position)
        scene.add(ring)
      }

      const geo = new THREE.SphereGeometry(size, 20, 20)
      const mat = new THREE.MeshStandardMaterial({
        color, emissive: color,
        emissiveIntensity: node.is_escape_node ? 1.2 : node.is_distraction ? 0.5 : 0.25,
        roughness: 0.2, metalness: 0.4,
        transparent: true,
        opacity: node.days_since_visit > 21 ? 0.2 : 1.0,
      })

      const mesh = new THREE.Mesh(geo, mat)
      mesh.position.set(x, y, z)
      scene.add(mesh)
      meshes.push(mesh)
      nodeMap.set(mesh, node)
    })

    // Session edges
    const sessionGroups = new Map<string, THREE.Vector3[]>()
    meshes.forEach(m => {
      const n = nodeMap.get(m)!
      if (!sessionGroups.has(n.session_id)) sessionGroups.set(n.session_id, [])
      sessionGroups.get(n.session_id)!.push(m.position.clone())
    })
    sessionGroups.forEach(positions => {
      if (positions.length < 2) return
      const geo = new THREE.BufferGeometry().setFromPoints(positions)
      const mat = new THREE.LineBasicMaterial({ color: 0x1e3a5f, transparent: true, opacity: 0.3 })
      scene.add(new THREE.Line(geo, mat))
    })

    // Interaction
    const raycaster = new THREE.Raycaster()
    raycaster.params.Points!.threshold = 0.5
    const mouse = new THREE.Vector2()
    let hoveredMesh: THREE.Mesh | null = null
    let dragging = false, lastX = 0, lastY = 0

    function onMouseMove(e: MouseEvent) {
      const rect = el.getBoundingClientRect()
      mouse.x =  ((e.clientX - rect.left) / W) * 2 - 1
      mouse.y = -((e.clientY - rect.top)  / H) * 2 + 1
      raycaster.setFromCamera(mouse, camera)
      const hits = raycaster.intersectObjects(meshes)
      if (hits.length > 0) {
        const mesh = hits[0].object as THREE.Mesh
        if (mesh !== hoveredMesh) {
          if (hoveredMesh) {
            const n = nodeMap.get(hoveredMesh)!
            ;(hoveredMesh.material as THREE.MeshStandardMaterial).emissiveIntensity =
              highlightUrls.size > 0 ? (highlightUrls.has(n.url) ? 2.5 : 0.05) : (n.is_escape_node ? 1.2 : 0.25)
          }
          hoveredMesh = mesh
          ;(mesh.material as THREE.MeshStandardMaterial).emissiveIntensity = 2.0
          setHovered(nodeMap.get(mesh)!)
          document.body.style.cursor = 'crosshair'
        }
      } else {
        if (hoveredMesh) {
          const n = nodeMap.get(hoveredMesh)!
          ;(hoveredMesh.material as THREE.MeshStandardMaterial).emissiveIntensity =
            highlightUrls.size > 0 ? (highlightUrls.has(n.url) ? 2.5 : 0.05) : (n.is_escape_node ? 1.2 : 0.25)
          hoveredMesh = null
        }
        setHovered(null)
        document.body.style.cursor = 'default'
      }
      if (dragging) {
        scene.rotation.y += (e.clientX - lastX) * 0.004
        scene.rotation.x += (e.clientY - lastY) * 0.004
        lastX = e.clientX; lastY = e.clientY
      }
    }

    function onMouseDown(e: MouseEvent) { dragging = true; lastX = e.clientX; lastY = e.clientY }
    function onMouseUp()   { dragging = false }
    function onClick()     { if (hoveredMesh) setSelected(s => s === nodeMap.get(hoveredMesh!) ? null : nodeMap.get(hoveredMesh!) ?? null) }
    function onWheel(e: WheelEvent) {
      camera.position.z = Math.max(20, Math.min(150, camera.position.z + e.deltaY * 0.04))
    }
    function onResize() {
      const W2 = el.clientWidth, H2 = el.clientHeight
      camera.aspect = W2 / H2
      camera.updateProjectionMatrix()
      renderer.setSize(W2, H2)
    }

    el.addEventListener('mousemove', onMouseMove)
    el.addEventListener('mousedown', onMouseDown)
    el.addEventListener('mouseup',   onMouseUp)
    el.addEventListener('click',     onClick)
    el.addEventListener('wheel',     onWheel)
    window.addEventListener('resize', onResize)

    let raf: number, t = 0
    function animate() {
      raf = requestAnimationFrame(animate)
      t += 0.003
      if (!dragging) {
        scene.rotation.y += 0.001
        // Pulse distraction nodes
        meshes.forEach(mesh => {
          const n = nodeMap.get(mesh)
          if (n?.is_distraction) {
            const mat = mesh.material as THREE.MeshStandardMaterial
            mat.emissiveIntensity = 0.4 + Math.sin(t * 3) * 0.2
          }
        })
      }
      renderer.render(scene, camera)
    }
    animate()

    return () => {
      cancelAnimationFrame(raf)
      el.removeEventListener('mousemove', onMouseMove)
      el.removeEventListener('mousedown', onMouseDown)
      el.removeEventListener('mouseup',   onMouseUp)
      el.removeEventListener('click',     onClick)
      el.removeEventListener('wheel',     onWheel)
      window.removeEventListener('resize', onResize)
      renderer.dispose()
      if (el.contains(renderer.domElement)) el.removeChild(renderer.domElement)
    }
  }, [nodes])

  const btnStyle = (active: boolean, color = '#60a5fa') => ({
    fontSize: 11, padding: '4px 12px', borderRadius: 4,
    border: active ? `1px solid ${color}44` : '1px solid #1e293b',
    cursor: 'pointer', fontFamily: "'Space Mono', monospace",
    background: active ? `${color}11` : 'transparent',
    color: active ? color : '#475569',
    transition: 'all 0.2s',
  } as React.CSSProperties)

  const deepestHole = rabbitHoles[0]

  return (
    <div id="scroll-container" style={{ height: '100vh', overflowY: 'scroll', scrollSnapType: 'y mandatory' }}>

      {/* ═══════════════════════════════════════════════════════
          SECTION 1: THE CONSTELLATION
      ═══════════════════════════════════════════════════════ */}
      <div className="section" style={{ background: '#020817' }}>
        {/* Three.js canvas */}
        <div ref={mountRef} style={{ position: 'absolute', inset: 0 }} />

        {/* Top bar */}
        <div style={{ position: 'absolute', top: 0, left: 0, right: 0, zIndex: 10, padding: '14px 20px', background: 'linear-gradient(to bottom, rgba(2,8,23,0.9) 0%, transparent 100%)' }}>
          <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12 }}>
            <div>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginBottom: 10 }}>
                <h1 style={{ color: 'white', fontSize: 18, fontWeight: 800, letterSpacing: '-0.5px', fontFamily: "'Syne', sans-serif" }}>
                  TAB CONSTELLATION
                </h1>
                <span style={{ fontSize: 10, color: '#1e3a5f', fontFamily: "'Space Mono', monospace" }}>
                  {nodes.length} nodes
                </span>
              </div>
              <div style={{ display: 'flex', gap: 6 }}>
                <input
                  type="text" placeholder="semantic search..." value={searchQuery}
                  onChange={e => setSearchQuery(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && runSearch(searchQuery)}
                  style={{ width: 200, fontSize: 11, padding: '5px 10px', background: 'rgba(15,23,42,0.8)', border: '1px solid #1e293b', borderRadius: 4, color: 'white', outline: 'none', fontFamily: "'Space Mono', monospace" }}
                />
                <button onClick={() => runSearch(searchQuery)} disabled={searching}
                  style={{ ...btnStyle(false), padding: '5px 10px' }}>
                  {searching ? '...' : 'SCAN'}
                </button>
                {highlightUrls.size > 0 && (
                  <button onClick={() => { setSearchQuery(''); setHighlightUrls(new Set()) }}
                    style={{ ...btnStyle(false), color: '#f87171', borderColor: '#f8717144' }}>
                    CLR
                  </button>
                )}
              </div>
              {highlightUrls.size > 0 && (
                <p style={{ color: '#60a5fa', fontSize: 10, marginTop: 4, fontFamily: "'Space Mono', monospace" }}>
                  ◉ {highlightUrls.size} signals detected
                </p>
              )}
            </div>

            {/* Cluster filters */}
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, justifyContent: 'flex-end', maxWidth: 500 }}>
              <button onClick={() => setActiveCluster(null)} style={btnStyle(activeCluster === null, 'white')}>ALL</button>
              {clusters.map(c => (
                <button key={c} onClick={() => setActiveCluster(activeCluster === c ? null : c)}
                  style={btnStyle(activeCluster === c, hex(cc(c)))}>
                  <span style={{ display: 'inline-block', width: 5, height: 5, borderRadius: '50%', background: hex(cc(c)), marginRight: 4 }} />
                  {c.toUpperCase()}
                </button>
              ))}
            </div>
          </div>

          {/* Controls row */}
          <div style={{ marginTop: 10, display: 'flex', alignItems: 'center', gap: 10 }}>
            <span style={{ color: '#1e3a5f', fontSize: 10, fontFamily: "'Space Mono', monospace" }}>RANGE</span>
            <input type="range" min={1} max={90} value={maxDays}
              onChange={e => setMaxDays(Number(e.target.value))}
              style={{ width: 90, accentColor: '#60a5fa' }} />
            <span style={{ color: '#334155', fontSize: 10, fontFamily: "'Space Mono', monospace" }}>{maxDays}D</span>
            <div style={{ marginLeft: 12, display: 'flex', gap: 6 }}>
              {([['🧠', 'focus', '#34d399'], ['🐇', 'rabbit', '#60a5fa'], ['⚡', 'distraction', '#f87171']] as [string, Panel, string][]).map(([icon, p, col]) => (
                <button key={p} onClick={() => setPanel(panel === p ? 'none' : p)} style={btnStyle(panel === p, col)}>
                  {icon} {p.toUpperCase()}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Loading */}
        {loading && (
          <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column', gap: 12 }}>
            <div style={{ width: 40, height: 40, border: '2px solid #1e3a5f', borderTop: '2px solid #60a5fa', borderRadius: '50%', animation: 'spin-slow 1s linear infinite' }} />
            <p style={{ color: '#334155', fontSize: 11, fontFamily: "'Space Mono', monospace" }}>INITIALIZING CONSTELLATION...</p>
          </div>
        )}

        {/* Hover tooltip */}
        {hovered && !selected && (
          <div style={{ position: 'absolute', bottom: 80, left: '50%', transform: 'translateX(-50%)', background: 'rgba(2,8,23,0.95)', border: '1px solid #1e293b', borderRadius: 4, padding: '10px 16px', color: 'white', fontSize: 12, textAlign: 'center', maxWidth: 360, zIndex: 20, pointerEvents: 'none', fontFamily: "'Syne', sans-serif" }}>
            <p style={{ fontWeight: 600, margin: 0 }}>{hovered.title}</p>
            <p style={{ margin: '3px 0 0', color: '#475569', fontSize: 10, fontFamily: "'Space Mono', monospace" }}>
              {hovered.domain}
              <span style={{ color: hex(cc(hovered.cluster)), margin: '0 6px' }}>●</span>
              {hovered.cluster.toUpperCase()}
              {hovered.time_spent > 0 && <span style={{ color: '#334155', marginLeft: 8 }}>{fmt(hovered.time_spent)}</span>}
            </p>
          </div>
        )}

        {/* Selected node panel */}
        {selected && (
          <div style={{ position: 'absolute', top: 120, right: 14, width: 280, background: 'rgba(2,8,23,0.97)', border: '1px solid #1e293b', borderRadius: 4, padding: 16, color: 'white', zIndex: 20 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
              <span style={{ fontSize: 10, padding: '2px 8px', border: `1px solid ${hex(cc(selected.cluster))}44`, color: hex(cc(selected.cluster)), fontFamily: "'Space Mono', monospace" }}>
                {selected.cluster.toUpperCase()}
              </span>
              <button onClick={() => setSelected(null)} style={{ background: 'none', border: 'none', color: '#334155', fontSize: 16, cursor: 'pointer' }}>✕</button>
            </div>
            <p style={{ fontWeight: 700, fontSize: 13, lineHeight: 1.4, marginBottom: 4, fontFamily: "'Syne', sans-serif" }}>{selected.title}</p>
            <p style={{ color: '#334155', fontSize: 10, marginBottom: 12, fontFamily: "'Space Mono', monospace" }}>{selected.domain}</p>
            {selected.meta_description && (
              <p style={{ color: '#475569', fontSize: 10, lineHeight: 1.6, marginBottom: 12, borderLeft: '2px solid #1e293b', paddingLeft: 8 }}>
                {selected.meta_description.slice(0, 100)}…
              </p>
            )}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6, marginBottom: 12 }}>
              {([
                ['FOCUS', `${(selected.focus_score * 100).toFixed(0)}%`],
                ['TIME', fmt(selected.time_spent ?? 0)],
                ['VISITS', String(selected.visit_count ?? 1)],
                ['DEPTH', String(selected.depth)],
                ['DISTRACTION', selected.is_distraction ? '⚠ YES' : '✓ NO'],
                ['ESCAPE', selected.is_escape_node ? '🚪 YES' : '—'],
              ] as [string, string][]).map(([label, val]) => (
                <div key={label} style={{ background: '#0a1224', padding: '7px 10px' }}>
                  <p style={{ margin: 0, color: '#334155', fontSize: 9, fontFamily: "'Space Mono', monospace" }}>{label}</p>
                  <p style={{ margin: '3px 0 0', fontWeight: 600, fontSize: 12 }}>{val}</p>
                </div>
              ))}
            </div>
            <a href={selected.url} target="_blank" rel="noreferrer"
              style={{ display: 'block', color: '#60a5fa', fontSize: 10, textDecoration: 'none', fontFamily: "'Space Mono', monospace", opacity: 0.7 }}>
              ↗ {selected.url.slice(0, 50)}{selected.url.length > 50 ? '…' : ''}
            </a>
          </div>
        )}

        {/* Insight panels */}
        {panel === 'focus' && focusSummary && (
          <div style={{ position: 'absolute', top: 120, left: 14, width: 280, background: 'rgba(2,8,23,0.97)', border: '1px solid #1e293b', borderRadius: 4, padding: 16, color: 'white', zIndex: 20 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 14 }}>
              <span style={{ fontWeight: 700, fontSize: 13, fontFamily: "'Syne', sans-serif" }}>🧠 FOCUS REPORT</span>
              <button onClick={() => setPanel('none')} style={{ background: 'none', border: 'none', color: '#334155', fontSize: 16, cursor: 'pointer' }}>✕</button>
            </div>
            <div style={{ textAlign: 'center', marginBottom: 16 }}>
              <div style={{ fontSize: 48, fontWeight: 800, color: focusSummary.avg_focus > 0.6 ? '#34d399' : '#f87171', fontFamily: "'Syne', sans-serif", lineHeight: 1 }}>
                {(focusSummary.avg_focus * 100).toFixed(0)}%
              </div>
              <div style={{ fontSize: 10, color: '#334155', fontFamily: "'Space Mono', monospace", marginTop: 4 }}>AVG FOCUS SCORE</div>
            </div>
            <div style={{ height: 4, background: '#0a1224', borderRadius: 99, marginBottom: 16, overflow: 'hidden' }}>
              <div style={{ height: 4, background: 'linear-gradient(to right, #34d399, #60a5fa)', width: `${focusSummary.avg_focus * 100}%`, transition: 'width 1s ease' }} />
            </div>
            {([
              ['TOTAL TIME', fmt(focusSummary.total_time)],
              ['FOCUS TIME', fmt(focusSummary.focus_time)],
              ['LOST TO DISTRACTIONS', fmt(focusSummary.distraction_time)],
            ] as [string, string][]).map(([l, v]) => (
              <div key={l} style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0', borderBottom: '1px solid #0a1224' }}>
                <span style={{ fontSize: 10, color: '#334155', fontFamily: "'Space Mono', monospace" }}>{l}</span>
                <span style={{ fontSize: 11, fontWeight: 600 }}>{v}</span>
              </div>
            ))}
          </div>
        )}

        {panel === 'rabbit' && (
          <div style={{ position: 'absolute', top: 120, left: 14, width: 300, maxHeight: 'calc(100vh - 150px)', background: 'rgba(2,8,23,0.97)', border: '1px solid #1e293b', borderRadius: 4, padding: 16, color: 'white', zIndex: 20, overflowY: 'auto' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 14 }}>
              <span style={{ fontWeight: 700, fontSize: 13, fontFamily: "'Syne', sans-serif" }}>🐇 RABBIT HOLES</span>
              <button onClick={() => setPanel('none')} style={{ background: 'none', border: 'none', color: '#334155', fontSize: 16, cursor: 'pointer' }}>✕</button>
            </div>
            {rabbitHoles.length === 0
              ? <p style={{ color: '#334155', fontSize: 11, fontFamily: "'Space Mono', monospace" }}>NO DEEP SESSIONS YET</p>
              : rabbitHoles.map((rh, i) => (
                <div key={i} style={{ marginBottom: 20, paddingBottom: 20, borderBottom: '1px solid #0a1224' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 10 }}>
                    <span style={{ fontSize: 10, color: '#475569', fontFamily: "'Space Mono', monospace" }}>
                      DEPTH {rh.max_depth} · {rh.node_count} TABS · {fmt(rh.total_time)}
                    </span>
                    {rh.has_distraction && <span style={{ fontSize: 9, color: '#f87171', border: '1px solid #f8717144', padding: '1px 6px', fontFamily: "'Space Mono', monospace" }}>DERAILED</span>}
                  </div>
                  {rh.chain.map((n, j) => (
                    <div key={j} style={{ display: 'flex', gap: 8, alignItems: 'flex-start', marginBottom: 4 }}>
                      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', paddingTop: 2 }}>
                        <div style={{ width: 7, height: 7, borderRadius: '50%', background: hex(cc(n.cluster)), flexShrink: 0, boxShadow: n.is_distraction ? `0 0 6px ${hex(cc(n.cluster))}` : 'none' }} />
                        {j < rh.chain.length - 1 && <div style={{ width: 1, height: 14, background: '#1e293b', marginTop: 2 }} />}
                      </div>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <p style={{ margin: 0, fontSize: 11, fontWeight: 600, color: n.is_distraction ? '#f87171' : 'white', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                          {n.title}
                        </p>
                        <p style={{ margin: 0, fontSize: 9, color: '#334155', fontFamily: "'Space Mono', monospace" }}>
                          {n.domain}{n.time_spent > 0 ? ` · ${fmt(n.time_spent)}` : ''}
                        </p>
                      </div>
                    </div>
                  ))}
                  <div style={{ display: 'flex', gap: 4, marginTop: 8, alignItems: 'center' }}>
                    <span style={{ fontSize: 9, color: hex(cc(rh.origin_cluster)), border: `1px solid ${hex(cc(rh.origin_cluster))}44`, padding: '1px 5px', fontFamily: "'Space Mono', monospace" }}>{rh.origin_cluster.toUpperCase()}</span>
                    <span style={{ fontSize: 9, color: '#334155' }}>→→→</span>
                    <span style={{ fontSize: 9, color: hex(cc(rh.exit_cluster)), border: `1px solid ${hex(cc(rh.exit_cluster))}44`, padding: '1px 5px', fontFamily: "'Space Mono', monospace" }}>{rh.exit_cluster.toUpperCase()}</span>
                  </div>
                </div>
              ))}
          </div>
        )}

        {panel === 'distraction' && distraction && (
          <div style={{ position: 'absolute', top: 120, left: 14, width: 280, background: 'rgba(2,8,23,0.97)', border: '1px solid #1e293b', borderRadius: 4, padding: 16, color: 'white', zIndex: 20 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 14 }}>
              <span style={{ fontWeight: 700, fontSize: 13, fontFamily: "'Syne', sans-serif" }}>⚡ DISTRACTION FINGERPRINT</span>
              <button onClick={() => setPanel('none')} style={{ background: 'none', border: 'none', color: '#334155', fontSize: 16, cursor: 'pointer' }}>✕</button>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 14 }}>
              <div style={{ background: '#0a1224', padding: '10px 12px' }}>
                <p style={{ margin: 0, color: '#334155', fontSize: 9, fontFamily: "'Space Mono', monospace" }}>HIJACKED TABS</p>
                <p style={{ margin: '4px 0 0', fontWeight: 800, fontSize: 24, color: '#f87171', fontFamily: "'Syne', sans-serif" }}>{distraction.total}</p>
              </div>
              <div style={{ background: '#0a1224', padding: '10px 12px' }}>
                <p style={{ margin: 0, color: '#334155', fontSize: 9, fontFamily: "'Space Mono', monospace" }}>TIME LOST</p>
                <p style={{ margin: '4px 0 0', fontWeight: 800, fontSize: 24, color: '#f87171', fontFamily: "'Syne', sans-serif" }}>{fmt(distraction.time_lost)}</p>
              </div>
            </div>
            <p style={{ fontSize: 10, color: '#334155', marginBottom: 10, fontFamily: "'Space Mono', monospace" }}>TOP OFFENDERS</p>
            {distraction.by_domain.slice(0, 5).map((d, i) => (
              <div key={i} style={{ marginBottom: 10 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 3 }}>
                  <span style={{ fontSize: 11, color: '#94a3b8' }}>{d.domain}</span>
                  <span style={{ fontSize: 10, color: '#475569', fontFamily: "'Space Mono', monospace" }}>{fmt(d.time_spent)}</span>
                </div>
                <div style={{ height: 2, background: '#0a1224' }}>
                  <div style={{ height: 2, background: `linear-gradient(to right, #f87171, #f97316)`, width: `${(d.time_spent / (distraction.by_domain[0]?.time_spent || 1)) * 100}%`, transition: 'width 1s ease' }} />
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Scroll hint */}
        {!loading && nodes.length > 0 && (
          <div style={{ position: 'absolute', bottom: 24, left: '50%', animation: 'scroll-bounce 2s ease-in-out infinite', zIndex: 10 }}>
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4 }}>
              <span style={{ fontSize: 9, color: '#1e3a5f', fontFamily: "'Space Mono', monospace", letterSpacing: 2 }}>EXPLORE DEEPER</span>
              <span style={{ color: '#1e3a5f', fontSize: 16 }}>↓</span>
            </div>
          </div>
        )}
      </div>

      {/* ═══════════════════════════════════════════════════════
          SECTION 2: THE WORMHOLE — Rabbit Hole Visualizer
      ═══════════════════════════════════════════════════════ */}
      <div className="section" style={{ background: 'radial-gradient(ellipse at center, #0a0a2e 0%, #020817 70%)' }}>
        <StarField id="wormhole-stars" />

        {/* Wormhole rings */}
        <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', pointerEvents: 'none' }}>
          {[...Array(8)].map((_, i) => (
            <div key={i} style={{
              position: 'absolute',
              width: 80 + i * 80, height: 80 + i * 80,
              border: `1px solid rgba(96,165,250,${0.15 - i * 0.015})`,
              borderRadius: '50%',
              animation: `spin-slow ${8 + i * 3}s linear infinite ${i % 2 === 0 ? '' : 'reverse'}`,
            }} />
          ))}
          <div style={{
            width: 60, height: 60,
            background: 'radial-gradient(circle, #60a5fa44 0%, transparent 70%)',
            borderRadius: '50%',
            boxShadow: '0 0 40px #60a5fa44, 0 0 80px #60a5fa22',
          }} />
        </div>

        <div style={{ position: 'relative', zIndex: 10, maxWidth: 900, width: '90%', display: 'flex', gap: 60, alignItems: 'center' }}>
          {/* Left: title */}
          <div style={{ flex: '0 0 280px' }}>
            <div style={{ fontSize: 10, color: '#1e3a5f', fontFamily: "'Space Mono', monospace", letterSpacing: 3, marginBottom: 12 }}>
              RABBIT HOLE DETECTED
            </div>
            <h2 style={{ fontSize: 42, fontWeight: 800, color: 'white', lineHeight: 1, marginBottom: 16, fontFamily: "'Syne', sans-serif" }}>
              THE<br />WORM<br />HOLE
            </h2>
            {deepestHole && (
              <>
                <div style={{ display: 'flex', gap: 16, marginBottom: 20 }}>
                  <div>
                    <div style={{ fontSize: 32, fontWeight: 800, color: '#60a5fa', fontFamily: "'Syne', sans-serif" }}>{deepestHole.max_depth}</div>
                    <div style={{ fontSize: 9, color: '#334155', fontFamily: "'Space Mono', monospace" }}>DEPTH</div>
                  </div>
                  <div>
                    <div style={{ fontSize: 32, fontWeight: 800, color: '#60a5fa', fontFamily: "'Syne', sans-serif" }}>{fmt(deepestHole.total_time)}</div>
                    <div style={{ fontSize: 9, color: '#334155', fontFamily: "'Space Mono', monospace" }}>LOST</div>
                  </div>
                  <div>
                    <div style={{ fontSize: 32, fontWeight: 800, color: '#60a5fa', fontFamily: "'Syne', sans-serif" }}>{deepestHole.node_count}</div>
                    <div style={{ fontSize: 9, color: '#334155', fontFamily: "'Space Mono', monospace" }}>HOPS</div>
                  </div>
                </div>
                <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                  <span style={{ fontSize: 10, padding: '3px 8px', border: `1px solid ${hex(cc(deepestHole.origin_cluster))}66`, color: hex(cc(deepestHole.origin_cluster)), fontFamily: "'Space Mono', monospace" }}>
                    {deepestHole.origin_cluster.toUpperCase()}
                  </span>
                  <span style={{ color: '#1e3a5f', fontSize: 12 }}>{'→'.repeat(Math.min(deepestHole.max_depth, 5))}</span>
                  <span style={{ fontSize: 10, padding: '3px 8px', border: `1px solid ${hex(cc(deepestHole.exit_cluster))}66`, color: hex(cc(deepestHole.exit_cluster)), fontFamily: "'Space Mono', monospace" }}>
                    {deepestHole.exit_cluster.toUpperCase()}
                  </span>
                </div>
              </>
            )}
            {!deepestHole && (
              <p style={{ color: '#334155', fontSize: 12, fontFamily: "'Space Mono', monospace" }}>BROWSE MORE TO DETECT RABBIT HOLES</p>
            )}
          </div>

          {/* Right: chain visualization */}
          {deepestHole && (
            <div style={{ flex: 1, maxHeight: '70vh', overflowY: 'auto' }}>
              <div style={{ position: 'relative', paddingLeft: 20 }}>
                {/* Vertical line */}
                <div style={{ position: 'absolute', left: 7, top: 8, bottom: 8, width: 1, background: 'linear-gradient(to bottom, #60a5fa, #f87171)' }} />

                {deepestHole.chain.map((node, i) => (
                  <div key={i} style={{ position: 'relative', marginBottom: 16, paddingLeft: 24, animation: `fade-up 0.5s ease ${i * 0.08}s both` }}>
                    {/* Node dot */}
                    <div style={{
                      position: 'absolute', left: 0, top: 4,
                      width: 14, height: 14, borderRadius: '50%',
                      background: node.is_distraction ? '#f87171' : hex(cc(node.cluster)),
                      boxShadow: `0 0 ${node.is_distraction ? 10 : 6}px ${node.is_distraction ? '#f87171' : hex(cc(node.cluster))}`,
                      border: '2px solid #020817',
                    }} />

                    <div style={{ background: node.is_distraction ? 'rgba(248,113,113,0.05)' : 'rgba(255,255,255,0.02)', border: `1px solid ${node.is_distraction ? '#f8717122' : '#1e293b'}`, padding: '8px 12px' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                        <p style={{ margin: 0, fontSize: 12, fontWeight: 600, color: node.is_distraction ? '#f87171' : 'white', flex: 1, paddingRight: 8 }}>
                          {node.title.length > 50 ? node.title.slice(0, 50) + '…' : node.title}
                        </p>
                        {node.time_spent > 0 && (
                          <span style={{ fontSize: 9, color: '#475569', fontFamily: "'Space Mono', monospace", flexShrink: 0 }}>{fmt(node.time_spent)}</span>
                        )}
                      </div>
                      <div style={{ display: 'flex', gap: 8, marginTop: 4, alignItems: 'center' }}>
                        <span style={{ fontSize: 9, color: '#334155', fontFamily: "'Space Mono', monospace" }}>{node.domain}</span>
                        <span style={{ fontSize: 9, color: hex(cc(node.cluster)), fontFamily: "'Space Mono', monospace" }}>● {node.cluster}</span>
                        {node.is_distraction && <span style={{ fontSize: 9, color: '#f87171', fontFamily: "'Space Mono', monospace" }}>⚠ DISTRACTION</span>}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* ═══════════════════════════════════════════════════════
          SECTION 3: THE CRASH SITE — Distraction Fingerprint
      ═══════════════════════════════════════════════════════ */}
      <div className="section" style={{ background: 'radial-gradient(ellipse at 30% 50%, #1a0a0a 0%, #020817 60%)' }}>
        <StarField id="crash-stars" />

        {/* Explosion particles */}
        <div style={{ position: 'absolute', inset: 0, pointerEvents: 'none' }}>
          {[...Array(20)].map((_, i) => {
            const angle = (i / 20) * 360
            const dist = 150 + Math.random() * 200
            return (
              <div key={i} style={{
                position: 'absolute',
                left: '50%', top: '50%',
                width: Math.random() * 3 + 1,
                height: Math.random() * 3 + 1,
                background: ['#f87171', '#f97316', '#fbbf24'][i % 3],
                borderRadius: '50%',
                transform: `translate(-50%, -50%) rotate(${angle}deg) translateX(${dist}px)`,
                opacity: Math.random() * 0.6 + 0.1,
                animation: `pulse-ring ${2 + Math.random() * 3}s ease-in-out infinite ${Math.random() * 2}s`,
              }} />
            )
          })}
        </div>

        <div style={{ position: 'relative', zIndex: 10, maxWidth: 900, width: '90%', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 60, alignItems: 'center' }}>
          {/* Right: viz */}
          <div>
            {distraction && (
              <>
                {/* Central crash indicator */}
                <div style={{ textAlign: 'center', marginBottom: 32 }}>
                  <div style={{
                    width: 120, height: 120, borderRadius: '50%', margin: '0 auto 16px',
                    background: 'radial-gradient(circle, #f8717133 0%, transparent 70%)',
                    border: '2px solid #f8717144',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    animation: 'pulse-ring 3s ease-in-out infinite',
                    boxShadow: '0 0 40px #f8717122',
                  }}>
                    <div style={{ fontSize: 36, fontWeight: 800, color: '#f87171', fontFamily: "'Syne', sans-serif" }}>
                      {fmt(distraction.time_lost)}
                    </div>
                  </div>
                  <p style={{ fontSize: 10, color: '#475569', fontFamily: "'Space Mono', monospace" }}>TOTAL TIME LOST</p>
                </div>

                {/* Domain bars */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                  {distraction.by_domain.slice(0, 5).map((d, i) => (
                    <div key={i}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                        <span style={{ fontSize: 12, color: '#94a3b8' }}>{d.domain}</span>
                        <span style={{ fontSize: 10, color: '#475569', fontFamily: "'Space Mono', monospace" }}>{fmt(d.time_spent)} · {d.visits}×</span>
                      </div>
                      <div style={{ height: 3, background: '#0a1224', overflow: 'hidden' }}>
                        <div style={{
                          height: 3,
                          background: `linear-gradient(to right, #f87171, #f97316)`,
                          width: `${(d.time_spent / (distraction.by_domain[0]?.time_spent || 1)) * 100}%`,
                          boxShadow: '0 0 8px #f87171',
                          transition: 'width 1.5s ease',
                        }} />
                      </div>
                    </div>
                  ))}
                </div>
              </>
            )}
          </div>

          {/* Left: title */}
          <div style={{ order: -1 }}>
            <div style={{ fontSize: 10, color: '#f87171', fontFamily: "'Space Mono', monospace", letterSpacing: 3, marginBottom: 12, opacity: 0.7 }}>
              ⚠ COLLISION DETECTED
            </div>
            <h2 style={{ fontSize: 48, fontWeight: 800, color: 'white', lineHeight: 0.95, marginBottom: 20, fontFamily: "'Syne', sans-serif" }}>
              THE<br /><span style={{ color: '#f87171' }}>CRASH</span><br />SITE
            </h2>
            <p style={{ fontSize: 13, color: '#475569', lineHeight: 1.7, marginBottom: 24, fontFamily: "'Syne', sans-serif" }}>
              Every distraction is a micro-collision. Your focus was interrupted {distraction?.total ?? 0} times, scattering your attention across the void.
            </p>
            {distraction && (
              <div style={{ display: 'flex', gap: 20 }}>
                {distraction.by_cluster.slice(0, 3).map((c, i) => (
                  <div key={i} style={{ textAlign: 'center' }}>
                    <div style={{ fontSize: 22, fontWeight: 800, color: '#f87171', fontFamily: "'Syne', sans-serif" }}>{c.count}</div>
                    <div style={{ fontSize: 9, color: '#334155', fontFamily: "'Space Mono', monospace", marginTop: 2 }}>{c.cluster.toUpperCase()}</div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ═══════════════════════════════════════════════════════
          SECTION 4: MISSION CONTROL — Focus Dashboard
      ═══════════════════════════════════════════════════════ */}
      <div className="section" style={{ background: 'radial-gradient(ellipse at 70% 50%, #0a1a0a 0%, #020817 60%)' }}>
        <StarField id="control-stars" />

        <div style={{ position: 'relative', zIndex: 10, maxWidth: 900, width: '90%' }}>
          <div style={{ textAlign: 'center', marginBottom: 48 }}>
            <div style={{ fontSize: 10, color: '#34d399', fontFamily: "'Space Mono', monospace", letterSpacing: 3, marginBottom: 12 }}>
              SYSTEM STATUS
            </div>
            <h2 style={{ fontSize: 48, fontWeight: 800, color: 'white', fontFamily: "'Syne', sans-serif" }}>
              MISSION CONTROL
            </h2>
          </div>

          {focusSummary && (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 2 }}>
              {/* Big focus gauge */}
              <div style={{ gridColumn: '1 / 2', background: '#0a1224', padding: 32, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
                <svg width="120" height="120" viewBox="0 0 120 120">
                  <circle cx="60" cy="60" r="50" fill="none" stroke="#0f172a" strokeWidth="8" />
                  <circle cx="60" cy="60" r="50" fill="none"
                    stroke={focusSummary.avg_focus > 0.6 ? '#34d399' : '#f87171'}
                    strokeWidth="8" strokeLinecap="round"
                    strokeDasharray="314"
                    strokeDashoffset={314 - (314 * focusSummary.avg_focus)}
                    transform="rotate(-90 60 60)"
                    style={{ transition: 'stroke-dashoffset 2s ease' }}
                  />
                  <text x="60" y="55" textAnchor="middle" fill="white" fontSize="20" fontWeight="800" fontFamily="Syne, sans-serif">
                    {(focusSummary.avg_focus * 100).toFixed(0)}%
                  </text>
                  <text x="60" y="72" textAnchor="middle" fill="#334155" fontSize="8" fontFamily="Space Mono, monospace">
                    FOCUS SCORE
                  </text>
                </svg>
              </div>

              {/* Stats grid */}
              {([
                ['NODES TRACKED', String(focusSummary.total_nodes), '#60a5fa'],
                ['FOCUS TIME', fmt(focusSummary.focus_time), '#34d399'],
                ['TIME LOST', fmt(focusSummary.distraction_time), '#f87171'],
                ['DISTRACTIONS', String(focusSummary.distraction_nodes), '#f97316'],
                ['EFFICIENCY', `${((focusSummary.focus_time / (focusSummary.total_time || 1)) * 100).toFixed(0)}%`, '#a78bfa'],
              ] as [string, string, string][]).map(([label, val, col]) => (
                <div key={label} style={{ background: '#0a1224', padding: '24px 28px', borderLeft: '2px solid transparent', borderImage: `linear-gradient(to bottom, ${col}, transparent) 1` }}>
                  <div style={{ fontSize: 9, color: '#334155', fontFamily: "'Space Mono', monospace", letterSpacing: 2, marginBottom: 8 }}>{label}</div>
                  <div style={{ fontSize: 28, fontWeight: 800, color: col, fontFamily: "'Syne', sans-serif" }}>{val}</div>
                </div>
              ))}
            </div>
          )}

          {/* Cluster breakdown */}
          <div style={{ marginTop: 2, background: '#0a1224', padding: '20px 28px' }}>
            <div style={{ fontSize: 9, color: '#334155', fontFamily: "'Space Mono', monospace", letterSpacing: 2, marginBottom: 16 }}>BROWSING SIGNATURE</div>
            <div style={{ display: 'flex', gap: 0, height: 8, overflow: 'hidden' }}>
              {clusters.map((cluster, i) => {
                const count = allNodes.filter(n => n.cluster === cluster).length
                const pct = (count / allNodes.length) * 100
                return (
                  <div key={cluster} title={`${cluster}: ${count} tabs`} style={{
                    width: `${pct}%`, height: 8,
                    background: hex(cc(cluster)),
                    transition: 'width 1s ease',
                  }} />
                )
              })}
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, marginTop: 12 }}>
              {clusters.map(cluster => {
                const count = allNodes.filter(n => n.cluster === cluster).length
                return (
                  <div key={cluster} style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                    <div style={{ width: 6, height: 6, background: hex(cc(cluster)), borderRadius: '50%' }} />
                    <span style={{ fontSize: 10, color: '#475569', fontFamily: "'Space Mono', monospace" }}>
                      {cluster} <span style={{ color: '#334155' }}>({count})</span>
                    </span>
                  </div>
                )
              })}
            </div>
          </div>
        </div>
      </div>

      {/* ═══════════════════════════════════════════════════════
          SECTION 5: THE VOID — Dead Stars & Guilt Pile
      ═══════════════════════════════════════════════════════ */}
      <div className="section" style={{ background: '#020817' }}>
        <StarField id="void-stars" />

        {/* Dead stars floating */}
        <div style={{ position: 'absolute', inset: 0, pointerEvents: 'none' }}>
          {allNodes.filter(n => n.days_since_visit > 7).slice(0, 12).map((n, i) => (
            <div key={i} style={{
              position: 'absolute',
              left: `${10 + (i * 7.5) % 80}%`,
              top: `${20 + (i * 11) % 60}%`,
              width: 8 + Math.random() * 12,
              height: 8 + Math.random() * 12,
              borderRadius: '50%',
              background: hex(cc(n.cluster)),
              opacity: 0.1 + Math.random() * 0.2,
              animation: `dead-pulse ${3 + Math.random() * 4}s ease-in-out infinite ${Math.random() * 3}s`,
            }} />
          ))}
        </div>

        <div style={{ position: 'relative', zIndex: 10, maxWidth: 700, width: '90%', textAlign: 'center' }}>
          <div style={{ fontSize: 10, color: '#334155', fontFamily: "'Space Mono', monospace", letterSpacing: 3, marginBottom: 16 }}>
            SECTOR: FORGOTTEN
          </div>
          <h2 style={{ fontSize: 56, fontWeight: 800, color: 'white', lineHeight: 0.9, marginBottom: 24, fontFamily: "'Syne', sans-serif" }}>
            THE<br />VOID
          </h2>
          <p style={{ fontSize: 14, color: '#334155', lineHeight: 1.8, marginBottom: 40, fontFamily: "'Syne', sans-serif" }}>
            Some tabs are opened with great intention.<br />
            Then never returned to.<br />
            They drift here — <span style={{ color: '#475569' }}>dimming slowly in the dark.</span>
          </p>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 2, marginBottom: 32 }}>
            {([
              ['TOTAL NODES', String(allNodes.length)],
              ['BROWSED TODAY', String(allNodes.filter(n => n.days_since_visit === 0).length)],
              ['FADING', String(allNodes.filter(n => n.days_since_visit > 7).length)],
            ] as [string, string][]).map(([l, v]) => (
              <div key={l} style={{ background: '#0a1224', padding: '20px 16px', textAlign: 'center' }}>
                <div style={{ fontSize: 32, fontWeight: 800, color: 'white', fontFamily: "'Syne', sans-serif" }}>{v}</div>
                <div style={{ fontSize: 9, color: '#334155', fontFamily: "'Space Mono', monospace", marginTop: 6 }}>{l}</div>
              </div>
            ))}
          </div>

          {allNodes.filter(n => n.days_since_visit > 7).length > 0 && (
            <div style={{ background: '#0a1224', padding: 20 }}>
              <div style={{ fontSize: 9, color: '#334155', fontFamily: "'Space Mono', monospace", letterSpacing: 2, marginBottom: 14 }}>FADING SIGNALS</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {allNodes.filter(n => n.days_since_visit > 7).slice(0, 5).map((n, i) => (
                  <div key={i} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '6px 0', borderBottom: '1px solid #0f172a' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, flex: 1, minWidth: 0 }}>
                      <div style={{ width: 6, height: 6, borderRadius: '50%', background: hex(cc(n.cluster)), opacity: 0.4, flexShrink: 0 }} />
                      <span style={{ fontSize: 11, color: '#334155', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{n.title}</span>
                    </div>
                    <span style={{ fontSize: 9, color: '#1e293b', fontFamily: "'Space Mono', monospace", flexShrink: 0, marginLeft: 12 }}>{n.days_since_visit}D AGO</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div style={{ marginTop: 40, fontSize: 9, color: '#1e293b', fontFamily: "'Space Mono', monospace", letterSpacing: 2 }}>
            TAB CONSTELLATION · BUILT WITH QDRANT VECTOR SEARCH
          </div>
        </div>
      </div>

    </div>
  )
}