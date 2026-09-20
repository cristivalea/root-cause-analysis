"""SUPERSEDED. This screen has been replaced by the interface in `rca/ui/`, which is run
with `streamlit run rca/ui/main.py`. It is kept for now so nothing depends on a file that
has disappeared; it is no longer maintained, and it expects a dark background
(`--theme.base dark`) because the new theme is light by default.

Technical Expert — standalone review page for RCA drafts.

Runs as a separate Streamlit app (its own port, its own process), independent from the
RCA investigation page. It reads the same SQLite store: the RCA page sends drafts
(PENDING_REVIEW), the expert approves one hypothesis, rejects everything or asks for
re-analysis, and the decision is written back to the same record, where the RCA page
picks it up.

Run: streamlit run rca/expert_app.py --server.port 8504
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st

from rca import store
from rca.config import DB_PATH

st.set_page_config(page_title="Expert Tehnic — RCA Review", page_icon="👤", layout="wide")

st.markdown(
    """
<style>
    .block-container { padding-top: 1.5rem; }
    .hero {
        background: linear-gradient(120deg, #2b1c4a 0%, #4a2b6b 55%, #6b2d8f 100%);
        border-radius: 14px;
        padding: 1.6rem 2.2rem;
        margin-bottom: 1.4rem;
        color: #fff;
    }
    .hero h1 { margin: 0; font-size: 1.9rem; }
    .hero p { margin: 0.4rem 0 0 0; color: #ddc3e8; }
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
    .inc-chip {
        display: inline-block; background: rgba(76,154,255,0.15); color: #8fb8ff;
        border-radius: 999px; padding: 0.2rem 0.8rem; margin: 0.2rem;
        font-size: 0.85rem; font-family: monospace;
    }
    .ev-line { font-size: 0.9rem; color: #c8d0dc; margin-bottom: 0.2rem; }
</style>
""",
    unsafe_allow_html=True,
)

st.markdown(
    """
<div class="hero">
    <h1>👤 Expert Tehnic</h1>
    <p>Drafturi RCA care așteaptă validarea ta. Primești ipotezele și incidentele
    similare, verifici evidence, apoi: validezi, ignori (respingi) sau ceri reanalizare.
    Răspunsul ajunge înapoi la aplicația RCA.</p>
</div>
""",
    unsafe_allow_html=True,
)

if st.button("🔄 Reîmprospătează lista", use_container_width=False):
    st.rerun()

pending = store.list_rcas(status="PENDING_REVIEW", db_path=DB_PATH)
if not pending:
    st.info("Nu există drafturi în așteptare. Când aplicația RCA trimite un draft, apare aici.")
    st.stop()

options = {f"{r.rca_id} · {r.incident_id} · {r.created_at:%Y-%m-%d %H:%M}": r for r in pending}
choice = st.selectbox("Draft în așteptare", list(options.keys()))
record = options[choice]

cols = st.columns(4)
cols[0].metric("RCA", record.rca_id)
cols[1].metric("Incident", record.incident_id)
cols[2].metric("Evidence", len(record.evidence))
if record.duration_seconds:
    cols[3].metric("Durată investigație", f"{record.duration_seconds:.0f}s")

if record.weakly_supported:
    st.warning("⚠️ Pipeline-ul marchează ipotezele ca slab susținute — verifică cu atenție.")

st.markdown(f"**Rezumat investigație:** {record.investigation_summary}")

# Incidentele similare primite
if record.linked_incidents:
    st.markdown("**Incidente similare primite:**")
    st.markdown(
        "".join(f'<span class="inc-chip">{i}</span>' for i in record.linked_incidents),
        unsafe_allow_html=True,
    )

tab_hyp, tab_ev, tab_plan = st.tabs(["🧠 Ipoteze", "📋 Evidence", "🗺️ Plan & Trace"])

with tab_hyp:
    for hyp in record.hypotheses:
        conf_class = f"conf-{hyp.confidence}"
        st.markdown('<div class="hyp-card">', unsafe_allow_html=True)
        hcols = st.columns([4, 1])
        hcols[0].markdown(f"**{hyp.hypothesis_id}** — {hyp.candidate_root_cause}")
        hcols[1].markdown(
            f'<span class="{conf_class}">{hyp.confidence}</span> ({hyp.confidence_points}p)',
            unsafe_allow_html=True,
        )
        with st.expander("Motive, dovezi, validare", expanded=False):
            st.markdown("**De ce:**")
            for r in hyp.reasons:
                st.markdown(f"- {r}")
            st.markdown(f"**Susținută de:** `{', '.join(hyp.supporting_evidence) or '—'}`")
            st.markdown(f"**Contra:** `{', '.join(hyp.contradicting_evidence) or '—'}`")
            st.markdown("**Validare recomandată:**")
            for v in hyp.recommended_validation:
                st.markdown(f"- {v}")
        st.markdown("</div>", unsafe_allow_html=True)
    if record.single_hypothesis_reason:
        st.caption(f"O singură ipoteză: {record.single_hypothesis_reason}")
    if record.suggested_workaround:
        st.success(f"**Workaround sugerat:** {record.suggested_workaround}")
    if record.not_checked:
        with st.expander("Ce nu s-a putut verifica"):
            for n in record.not_checked:
                st.markdown(f"- {n}")

with tab_ev:
    icons = {"CHANGE": "🔧", "LOG_GROUP": "📄", "CMDB_DEPENDENCY": "🔗",
             "HISTORICAL_RCA": "📚", "SIMILAR_INCIDENT": "🔁"}
    for ev in record.evidence:
        icon = icons.get(ev.type, "•")
        ts = f" · {ev.timestamp:%Y-%m-%d %H:%M}" if ev.timestamp else ""
        st.markdown(
            f'<div class="ev-line">{icon} <b>{ev.evidence_id}</b> [{ev.type}] '
            f'{ev.description} — <i>{ev.citation}{ts}</i></div>',
            unsafe_allow_html=True,
        )

with tab_plan:
    if record.plan:
        plan = record.plan
        st.markdown(f"**Serviciu:** `{plan.service}`")
        if plan.related_services:
            st.markdown(f"**Servicii dependente:** {', '.join(f'`{s}`' for s in plan.related_services)}")
        st.markdown(f"**Fereastră:** {plan.window_start:%Y-%m-%d %H:%M} → {plan.window_end:%Y-%m-%d %H:%M} UTC")
        st.markdown(f"**Surse:** {', '.join(plan.sources)}")
        st.info(f"**Raționament:** {plan.rationale}")
    if record.trace:
        st.markdown("**Pașii investigației:**")
        for step in record.trace:
            dur = ""
            if step.finished_at and step.started_at:
                dur = f" · {(step.finished_at - step.started_at).total_seconds():.1f}s"
            st.markdown(f"- **{step.name}**{dur} — {step.summary}")

# ---------- Decizia ----------
st.divider()
st.markdown("### ✍️ Decizia ta")

reviewer = st.text_input("Numele tău", value="Technical Expert")
comment = st.text_area("Comentariu (obligatoriu pentru respingere / reanalizare)")

if record.hypotheses:
    hyp_labels = {
        f"{h.hypothesis_id} — {h.candidate_root_cause[:80]}": h.hypothesis_id
        for h in record.hypotheses
    }
    chosen = st.selectbox("Ipoteza de validat", list(hyp_labels.keys()))
else:
    hyp_labels, chosen = {}, None

cols = st.columns(3)
if cols[0].button("✅ Validează analiza", type="primary", use_container_width=True,
                  disabled=not hyp_labels):
    try:
        updated = store.apply_review(
            record.rca_id, reviewer, "APPROVE", comment or "Approved.", hyp_labels[chosen],
            db_path=DB_PATH,
        )
    except ValueError as exc:
        st.error(str(exc))
    else:
        st.success(f"{updated.rca_id} → FINAL. Cauza: {updated.final_root_cause}")
        st.rerun()
if cols[1].button("❌ Ignoră (respinge)", use_container_width=True):
    if not comment.strip():
        st.error("La respingere comentariul este obligatoriu.")
    else:
        store.apply_review(record.rca_id, reviewer, "REJECT", comment, db_path=DB_PATH)
        st.warning(f"{record.rca_id} a fost respins.")
        st.rerun()
if cols[2].button("🔁 Cere reanalizare", use_container_width=True):
    if not comment.strip():
        st.error("La reanalizare comentariul este obligatoriu.")
    else:
        store.apply_review(record.rca_id, reviewer, "REANALYZE", comment, db_path=DB_PATH)
        st.info(f"{record.rca_id} a fost trimis înapoi la investigație (INVESTIGATING).")
        st.rerun()
