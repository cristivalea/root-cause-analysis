"""SUPERSEDED. This screen has been replaced by the interface in `rca/ui/`, which is run
with `streamlit run rca/ui/main.py`. It is kept for now so nothing depends on a file that
has disappeared; it is no longer maintained, and it expects a dark background
(`--theme.base dark`) because the new theme is light by default.

Problem Management AI — Streamlit interface for the RCA investigation pipeline.

One page, three views:
1. The incident list — pick an incident (menu: filters, add, delete, reload from sources).
2. The analysis page — after "Începe RCA": the LangGraph run live, every state with the
   tools it used, what went in and what came out, then the full result.
3. The result stays a DRAFT until the Problem Manager presses "Trimite la Expertul
   Tehnic" — only then the record becomes PENDING_REVIEW. Nothing is sent automatically.
"""

import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st

from rca import storage, store
from rca.config import DB_PATH
from rca.models import Incident, RCARecord
from rca.pipeline import run_investigation

st.set_page_config(page_title="Problem Management AI", page_icon="🔍", layout="wide")

SOURCES_DIR = Path(__file__).resolve().parent.parent / "data" / "sources"

SEVERITY_STYLE = {
    "SEV-1": ("#FF5630", "Critic"),
    "SEV-2": ("#FFAB00", "Major"),
    "SEV-3": ("#4C9AFF", "Minor"),
}

# The states of the graph, in execution order (guardrail → reasoning is the retry loop).
GRAPH_NODES = [
    ("start", "Start", "Încarcă incidentul din SQLite"),
    ("similar_incidents", "Incidente similare", "Tool: căutare semantică ChromaDB"),
    ("investigation_planner", "Planner (LLM)", "Agent: decide serviciu, fereastră, surse"),
    ("tools", "Tools", "CMDB · changes · logs · RCA-uri istorice"),
    ("historical_rca_agent", "Historical RCA (LLM)", "Agent: judecă relevanța RCA-urilor"),
    ("rca_reasoning_agent", "Reasoning (LLM)", "Agent: ipoteze de cauză cu citații"),
    ("guardrail", "Guardrails", "Cod: validează citațiile și structura"),
    ("confidence", "Confidence", "Cod: scor din evidence, nu din model"),
    ("save_rca", "Salvare", "Scrie recordul în SQLite"),
]

STEP_EXPLAIN = {
    "start": ("Incident din `incidents` (SQLite)", "obiect `Incident` validat"),
    "similar_incidents": ("textul incidentului → căutare semantică", "listă de incidente similare"),
    "investigation_planner": ("incident + incidente similare → LLM (JSON)", "`InvestigationPlan` validat Pydantic"),
    "tools": ("planul (serviciu, fereastră, surse)", "evidence `EV-…` în ledger"),
    "historical_rca_agent": ("plan + secțiuni RCA → LLM (JSON)", "decizii relevant/not + evidence"),
    "rca_reasoning_agent": ("evidence ledger → LLM (JSON)", "`DraftRCA` cu ipoteze"),
    "guardrail": ("draftul", "OK sau probleme → retry la reasoning"),
    "confidence": ("ipoteze + evidence", "`AssessedHypothesis` cu scor"),
    "save_rca": ("starea finală", "`RCARecord` salvat (PENDING_REVIEW)"),
}

# ---------- Styling ----------
if st.session_state.get("view") in ("analyzing", "result"):
    # Full-screen analysis: no sidebar menu, no default header — only the analysis.
    st.markdown(
        """
<style>
    [data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"],
    [data-testid="stHeader"] { display: none !important; }
    .block-container { padding-top: 1rem; }
</style>
""",
        unsafe_allow_html=True,
    )

st.markdown(
    """
<style>
    .block-container { padding-top: 1.5rem; }
    .hero {
        background: linear-gradient(120deg, #1c2b4a 0%, #243b6b 55%, #2d4f8f 100%);
        border-radius: 14px;
        padding: 1.6rem 2.2rem;
        margin-bottom: 1.4rem;
        color: #fff;
    }
    .hero h1 { margin: 0; font-size: 1.9rem; }
    .hero p { margin: 0.4rem 0 0 0; color: #c3d0e8; }
    .inc-card {
        background: rgba(255,255,255,0.04);
        border: 1px solid rgba(255,255,255,0.10);
        border-top: 4px solid #4C9AFF;
        border-radius: 10px;
        padding: 0.9rem 1rem 0.6rem 1rem;
        margin-bottom: 0.4rem;
        min-height: 9.5rem;
    }
    .inc-selected { outline: 2px solid #36B37E; }
    .inc-id { font-family: monospace; color: #9aa5b1; font-size: 0.8rem; }
    .inc-title { font-weight: 600; font-size: 1.0rem; margin: 0.25rem 0; line-height: 1.3; }
    .inc-service { color: #9aa5b1; font-size: 0.85rem; }
    .sev-pill {
        display: inline-block; padding: 0.1rem 0.6rem; border-radius: 999px;
        font-size: 0.75rem; font-weight: 700; color: #fff;
    }
    .ev-card {
        background: rgba(255,255,255,0.04);
        border: 1px solid rgba(255,255,255,0.12);
        border-left: 4px solid #4C9AFF;
        border-radius: 8px;
        padding: 0.7rem 1rem;
        margin-bottom: 0.5rem;
    }
    .ev-id { color: #4C9AFF; font-weight: 700; font-family: monospace; }
    .ev-cite { color: #9aa5b1; font-size: 0.85rem; font-family: monospace; }
    .hyp-card {
        background: rgba(255,255,255,0.04);
        border: 1px solid rgba(255,255,255,0.12);
        border-radius: 10px;
        padding: 1rem 1.2rem;
        margin-bottom: 0.8rem;
    }
    .conf-HIGH { color: #36B37E; font-weight: 700; }
    .conf-MEDIUM { color: #FFAB00; font-weight: 700; }
    .conf-LOW { color: #FF5630; font-weight: 700; }
    .status-badge {
        display: inline-block; padding: 0.2rem 0.8rem; border-radius: 999px;
        font-weight: 600; font-size: 0.85rem;
    }
    .status-PENDING_REVIEW { background: #FFAB0033; color: #FFAB00; }
    .status-DRAFT { background: #4C9AFF33; color: #4C9AFF; }
    .status-FINAL { background: #36B37E33; color: #36B37E; }
    .status-ESCALATED { background: #FF563033; color: #FF5630; }
    .status-REJECTED { background: #FF563033; color: #FF5630; }
    .status-INVESTIGATING { background: #4C9AFF33; color: #4C9AFF; }
    .sym-chip {
        display: inline-block; background: rgba(76,154,255,0.15); color: #8fb8ff;
        border-radius: 999px; padding: 0.15rem 0.7rem; margin: 0.15rem;
        font-size: 0.82rem;
    }
    .node-chip {
        display: inline-block; border-radius: 8px; padding: 0.35rem 0.7rem;
        margin: 0.2rem; font-size: 0.82rem; font-weight: 600;
        border: 1px solid rgba(255,255,255,0.15);
    }
    .node-done { background: #36B37E22; color: #36B37E; border-color: #36B37E66; }
    .node-running { background: #FFAB0022; color: #FFAB00; border-color: #FFAB0066; }
    .node-pending { background: rgba(255,255,255,0.04); color: #6b7686; }
    .node-arrow { color: #6b7686; }
</style>
""",
    unsafe_allow_html=True,
)


@st.cache_data(show_spinner=False)
def load_incidents() -> list[Incident]:
    """The incidents from the source database — the same source the pipeline investigates."""
    try:
        return storage.list_incidents(DB_PATH)
    except FileNotFoundError:
        return []


def next_incident_id() -> str:
    year = datetime.now(timezone.utc).year
    ids = [i.incident_id for i in load_incidents() if i.incident_id.startswith(f"INC-{year}-")]
    number = max((int(i.rsplit("-", 1)[1]) for i in ids), default=0) + 1
    return f"INC-{year}-{number:05d}"


def render_add_form() -> None:
    st.markdown("### ➕ Adaugă un incident nou")
    with st.form("add_incident", clear_on_submit=True):
        cols = st.columns(3)
        inc_id = cols[0].text_input("ID incident", value=next_incident_id())
        severity = cols[1].selectbox("Severitate", ["SEV-1", "SEV-2", "SEV-3", "SEV-4"])
        status = cols[2].selectbox("Status", ["Resolved", "Closed"])
        title = st.text_input("Titlu*")
        description = st.text_area("Descriere*")
        cols = st.columns(3)
        service = cols[0].text_input("Serviciu tehnic*", placeholder="Payment API")
        business_service = cols[1].text_input("Serviciu business*", placeholder="Online Payments")
        environment = cols[2].selectbox("Mediu", ["production", "test"])
        cols = st.columns(3)
        detected = cols[0].datetime_input("Detectat la (UTC)*", value=datetime.now(timezone.utc).replace(tzinfo=None))
        symptoms_raw = st.text_input("Simptome (separate prin virgulă)*", placeholder="HTTP 500, latency spikes")
        mitigation = st.text_input("Mitigare inițială")
        rca_reason = st.text_input("De ce este nevoie de RCA")
        submitted = st.form_submit_button("💾 Salvează incidentul", type="primary", use_container_width=True)

    if submitted:
        if not (title.strip() and description.strip() and service.strip() and business_service.strip() and symptoms_raw.strip()):
            st.error("Completează câmpurile obligatorii (*).")
            return
        incident = Incident(
            incident_id=inc_id.strip(), title=title.strip(), description=description.strip(),
            severity=severity, status=status, service=service.strip(),
            business_service=business_service.strip(), environment=environment,
            detected_at=detected.replace(tzinfo=timezone.utc),
            symptoms=[s.strip() for s in symptoms_raw.split(",") if s.strip()],
            initial_mitigation=mitigation.strip() or None,
            rca_required=True, rca_reason=rca_reason.strip() or None,
        )
        try:
            storage.upsert_incident(DB_PATH, incident)
        except Exception as exc:
            st.error(f"Nu am putut salva: {exc}")
            return
        load_incidents.clear()
        st.success(f"Incidentul {incident.incident_id} a fost salvat.")
        st.rerun()


def render_delete() -> None:
    st.markdown("### 🗑️ Șterge un incident")
    incidents = load_incidents()
    if not incidents:
        st.info("Nu există incidente în baza de date.")
        return
    options = {f"{i.incident_id} — {i.title}": i.incident_id for i in incidents}
    choice = st.selectbox("Incident", list(options.keys()))
    st.warning("Ștergerea este definitivă și elimină incidentul din sursa investigației.")
    if st.button("🗑️ Șterge definitiv", use_container_width=True):
        storage.delete_incident(DB_PATH, options[choice])
        load_incidents.clear()
        st.success(f"Incidentul {options[choice]} a fost șters.")
        st.rerun()


def render_list(incidents: list[Incident]) -> None:
    sev_filter = st.sidebar.pills("Severitate", list(SEVERITY_STYLE.keys()), selection_mode="multi",
                                default=list(SEVERITY_STYLE.keys()))
    services = sorted({i.service for i in incidents})
    svc_filter = st.sidebar.multiselect("Serviciu", services)
    env_filter = st.sidebar.multiselect("Mediu", ["production", "test"])
    search = st.sidebar.text_input("Caută în titlu/descriere")

    filtered = [
        i for i in incidents
        if i.severity in (sev_filter or [])
        and (not svc_filter or i.service in svc_filter)
        and (not env_filter or i.environment in env_filter)
        and (not search or search.lower() in (i.title + i.description).lower())
    ]
    st.caption(f"{len(filtered)} din {len(incidents)} incidente")

    selected_id = (st.session_state.get("selected") or {}).get("incident_id")
    for row_start in range(0, len(filtered), 3):
        cols = st.columns(3)
        for col, inc in zip(cols, filtered[row_start:row_start + 3]):
            with col:
                color, label = SEVERITY_STYLE.get(inc.severity, ("#4C9AFF", inc.severity))
                selected = inc.incident_id == selected_id
                st.markdown(
                    f'<div class="inc-card {"inc-selected" if selected else ""}" style="border-top-color:{color}">'
                    f'<span class="sev-pill" style="background:{color}">{inc.severity} · {label}</span>'
                    f'<div class="inc-title">{inc.title}</div>'
                    f'<div class="inc-service">🛠️ {inc.service} · 📅 {inc.detected_at:%Y-%m-%d}</div>'
                    f'<div class="inc-id">{inc.incident_id}</div>'
                    f"</div>",
                    unsafe_allow_html=True,
                )
                btn_label = "✅ Selectat" if selected else "Selectează"
                if st.button(btn_label, key=f"pick-{inc.incident_id}", use_container_width=True,
                             type="primary" if selected else "secondary"):
                    st.session_state["selected"] = inc.model_dump(mode="json")
                    st.rerun()


def render_graph(done_steps: list[str], running: str | None, container=None) -> None:
    """The investigation graph as chips: done (green), running (yellow), pending (gray)."""
    parts = []
    for key, label, hint in GRAPH_NODES:
        if key in done_steps:
            cls, icon = "node-done", "✓"
        elif key == running:
            cls, icon = "node-running", "▶"
        else:
            cls, icon = "node-pending", "○"
        parts.append(f'<span class="node-chip {cls}" title="{hint}">{icon} {label}</span>')
    html = '<div>' + '<span class="node-arrow">→</span>'.join(parts) + "</div>"
    (container.markdown if container is not None else st.markdown)(html, unsafe_allow_html=True)


def render_step_details(steps) -> None:
    """What happened in each finished state: tools, inputs, outputs (from the step details)."""
    for step in steps:
        io_in, io_out = STEP_EXPLAIN.get(step.name, ("", ""))
        dur = ""
        if step.finished_at and step.started_at:
            dur = f"{(step.finished_at - step.started_at).total_seconds():.1f}s"
        with st.expander(f"✔ {step.name} · {dur}", expanded=False):
            st.markdown(f"**Ce s-a întâmplat:** {step.summary}")
            if io_in:
                st.markdown(f"**Intrare:** {io_in}")
            if io_out:
                st.markdown(f"**Ieșire:** {io_out}")
            if step.details:
                st.json(step.details, expanded=False)


def render_evidence(record: RCARecord) -> None:
    icons = {"CHANGE": "🔧", "LOG_GROUP": "📄", "CMDB_DEPENDENCY": "🔗", "HISTORICAL_RCA": "📚", "SIMILAR_INCIDENT": "🔁"}
    for ev in record.evidence:
        icon = icons.get(ev.type, "•")
        ts = f" · {ev.timestamp:%Y-%m-%d %H:%M}" if ev.timestamp else ""
        st.markdown(
            f'<div class="ev-card">{icon} <span class="ev-id">{ev.evidence_id}</span> '
            f'<b>[{ev.type}]</b> {ev.description}<br>'
            f'<span class="ev-cite">sursa: {ev.citation}{ts}</span></div>',
            unsafe_allow_html=True,
        )


def render_hypotheses(record: RCARecord) -> None:
    for hyp in record.hypotheses:
        conf_class = f"conf-{hyp.confidence}"
        st.markdown('<div class="hyp-card">', unsafe_allow_html=True)
        cols = st.columns([4, 1])
        cols[0].markdown(f"**{hyp.hypothesis_id}** — {hyp.candidate_root_cause}")
        cols[1].markdown(f'<span class="{conf_class}">{hyp.confidence}</span> ({hyp.confidence_points}p)', unsafe_allow_html=True)
        with st.expander("Detalii", expanded=False):
            st.markdown("**De ce:**")
            for r in hyp.reasons:
                st.markdown(f"- {r}")
            st.markdown(f"**Susținută de:** `{', '.join(hyp.supporting_evidence) or '—'}`")
            st.markdown(f"**Contra:** `{', '.join(hyp.contradicting_evidence) or '—'}`")
            st.markdown("**Validare recomandată:**")
            for v in hyp.recommended_validation:
                st.markdown(f"- {v}")
        st.markdown("</div>", unsafe_allow_html=True)


def render_record(record: RCARecord) -> None:
    cols = st.columns(4)
    cols[0].metric("RCA", record.rca_id)
    cols[1].markdown(f"**Status**<br><span class='status-badge status-{record.status}'>{record.status}</span>", unsafe_allow_html=True)
    cols[2].metric("Evidence", len(record.evidence))
    if record.duration_seconds:
        cols[3].metric("Durată", f"{record.duration_seconds:.0f}s")

    if record.weakly_supported:
        st.warning("⚠️ Ipotezele sunt slab susținute de evidence — este nevoie de mai multă investigație.")

    tab1, tab2, tab3, tab4 = st.tabs(["🗺️ Plan", "📋 Evidence", "🧠 Ipoteze & Draft", "🧾 Graf execuție"])

    with tab1:
        if record.plan:
            plan = record.plan
            st.markdown(f"**Serviciu:** `{plan.service}`")
            if plan.related_services:
                st.markdown(f"**Servicii dependente:** {', '.join(f'`{s}`' for s in plan.related_services)}")
            st.markdown(f"**Fereastră:** {plan.window_start:%Y-%m-%d %H:%M} → {plan.window_end:%Y-%m-%d %H:%M} UTC")
            st.markdown(f"**Surse:** {', '.join(plan.sources)}")
            st.markdown("**Query-uri de căutare:**")
            for q in plan.search_queries:
                st.markdown(f"- _{q}_")
            st.info(f"**Raționament:** {plan.rationale}")
        if record.linked_incidents:
            st.markdown(f"**Incidente similare legate:** {', '.join(f'`{i}`' for i in record.linked_incidents)}")

    with tab2:
        render_evidence(record)

    with tab3:
        st.markdown(f"**Rezumat investigație:** {record.investigation_summary}")
        if record.observed_patterns:
            with st.expander("Tipare observate", expanded=True):
                for p in record.observed_patterns:
                    st.markdown(f"- {p}")
        render_hypotheses(record)
        if record.single_hypothesis_reason:
            st.caption(f"O singură ipoteză: {record.single_hypothesis_reason}")
        cols = st.columns(2)
        with cols[0]:
            if record.suggested_workaround:
                st.success(f"**Workaround sugerat:** {record.suggested_workaround}")
        with cols[1]:
            if record.change_likely_required:
                st.info("🔧 Rezolvarea cauzei necesită probabil un Change Request.")
        if record.not_checked:
            with st.expander("Ce nu s-a putut verifica"):
                for n in record.not_checked:
                    st.markdown(f"- {n}")

    with tab4:
        render_graph([s.name for s in record.trace], None)
        st.divider()
        render_step_details(record.trace)

    if record.status == "DRAFT":
        st.divider()
        st.markdown("### 📨 Trimitere către Expertul Tehnic")
        st.caption("Draftul nu se trimite automat. Verifică rezultatul, apoi trimite-l tu. "
                   "Expertul îl vede pe pagina lui separată (rca/expert_app.py).")
        if st.button("📨 Trimite la Expertul Tehnic", type="primary", use_container_width=True):
            updated = store.submit_for_review(record.rca_id, db_path=DB_PATH)
            st.session_state["record"] = updated
            st.rerun()
    elif record.status == "PENDING_REVIEW":
        st.divider()
        st.info("📨 Draftul a fost trimis către Expertul Tehnic și așteaptă decizia.")
        if st.button("🔍 Verifică răspunsul", use_container_width=True):
            latest = store.get_rca(record.rca_id, db_path=DB_PATH)
            if latest is not None and latest.status != "PENDING_REVIEW":
                st.session_state["record"] = latest
                show_expert_answer(latest)
            else:
                st.caption("Încă nu a răspuns. Încearcă din nou în câteva secunde.")
    elif record.review is not None:
        st.divider()
        show_expert_answer(record)


@st.dialog("📬 Răspunsul Expertului Tehnic", width="large")
def _expert_answer_dialog(record: RCARecord) -> None:
    review = record.review
    if review is None:
        st.write("Fără decizie încă.")
        return
    st.markdown(f"**{record.rca_id}** · decis de **{review.reviewer}** · {review.decided_at:%Y-%m-%d %H:%M}")
    if review.decision == "APPROVE":
        st.success(f"✅ **Aprobat** — ipoteza `{review.hypothesis_id}`")
        st.markdown(f"**Cauza finală:** {record.final_root_cause}")
        st.markdown(f"Status: `FINAL`")
    elif review.decision == "REJECT":
        st.error("❌ **Respins** — întreaga analiză")
        st.markdown(f"Status: `REJECTED`")
    st.markdown(f"**Comentariu:** {review.comment}")


def show_expert_answer(record: RCARecord) -> None:
    """Pop-up with the expert's decision, when it arrived."""
    if record.review is not None:
        _expert_answer_dialog(record)


def run_pipeline(incident_id: str) -> None:
    """The analysis page: the graph runs live, then the result stays as a draft."""
    st.markdown("#### 🔄 Graful investigației — execuție live")
    graph_box = st.empty()
    status_box = st.status("Investigația rulează...", expanded=True)
    done: list[str] = []
    steps = []
    with graph_box.container():
        render_graph(done, GRAPH_NODES[0][0])

    def on_step(step):
        done.append(step.name)
        steps.append(step)
        with graph_box.container():
            render_graph(done, None)
        with status_box:
            render_step_details(steps[-1:])

    t0 = time.time()
    try:
        record = run_investigation(incident_id, on_step=on_step)
    except Exception as e:
        status_box.update(label="Investigația a eșuat", state="error")
        st.exception(e)
        if st.button("← Înapoi la incidente"):
            st.session_state["view"] = "list"
            st.rerun()
        st.stop()
    status_box.update(label=f"Investigație finalizată în {time.time() - t0:.0f}s", state="complete", expanded=False)
    st.session_state["record"] = record
    st.session_state["view"] = "result"
    st.rerun()


# ---------- Page 1: RCA ----------
def page_rca() -> None:
    view = st.session_state.get("view", "list")

    # ----- Pagina de analiză: fără listă, fără meniu -----
    if view == "analyzing":
        inc = st.session_state["selected"]
        if st.button("✕ Anulează și revino la incidente"):
            st.session_state["view"] = "list"
            st.session_state.pop("selected", None)
            st.rerun()
        st.markdown(f"## 🔍 Analiză RCA — `{inc['incident_id']}`")
        st.subheader(inc["title"])
        st.caption(f"🛠️ {inc['service']} · 📅 {inc['detected_at'][:10]} · {inc['severity']}")
        st.divider()
        run_pipeline(inc["incident_id"])
        return

    if view == "result":
        if st.button("← Înapoi la incidente"):
            st.session_state.pop("record", None)
            st.session_state.pop("selected", None)
            st.session_state["view"] = "list"
            st.rerun()
        render_record(st.session_state["record"])
        return

    # ----- Pagina principală: lista de incidente -----
    st.markdown(
        """
<div class="hero">
    <h1>🔍 Investigație RCA</h1>
    <p>Alege un incident din listă și pornește investigația. Analiza rulează pe o pagină
    dedicată, ca un graf LangGraph live, iar la final decizi tu dacă o trimiți la expert.</p>
</div>
""",
        unsafe_allow_html=True,
    )

    # Tot conținutul listei stă într-un container gol: dispare complet în celelalte view-uri.
    page_box = st.empty()
    with page_box.container():
        # ----- Meniu -----
        action = st.sidebar.radio(
            "Meniu incidente",
            ["📋 Listare & filtre", "➕ Adaugă incident", "🗑️ Șterge incident"],
        )
        st.sidebar.divider()
        if st.sidebar.button("🔄 Reîncarcă noile incidente", use_container_width=True):
            with st.spinner("Reîncarc sursele în baza de date..."):
                try:
                    storage.load_sources(DB_PATH, SOURCES_DIR)
                except Exception as exc:
                    st.sidebar.error(f"Reîncărcarea a eșuat: {exc}")
                else:
                    load_incidents.clear()
                    st.sidebar.success("Incidentele au fost reîncărcate din surse.")
                    st.rerun()

        # ----- Conținut -----
        if action == "➕ Adaugă incident":
            render_add_form()
            return
        if action == "🗑️ Șterge incident":
            render_delete()
            return

        incidents = load_incidents()
        if not incidents:
            st.warning("Baza de date nu are incidente. Folosește **🔄 Reîncarcă noile incidente** din meniu.")
            return
        render_list(incidents)

        if "selected" in st.session_state and view == "list":
            inc = st.session_state["selected"]
            st.divider()
            st.markdown(f"**Incident selectat:** `{inc['incident_id']}` — {inc['title']}")
            st.caption(f"De ce RCA: {inc.get('rca_reason') or '—'}")
            if st.button("🚀 Începe RCA", type="primary", use_container_width=True):
                st.session_state["view"] = "analyzing"
                st.rerun()


# ---------- App ----------
page_rca()