# Arhitectura proiect Root cause analysis

# Arhitectură — Agenți

Sistemul separă strict **reasoning** (propus de LLM, output JSON validat) de **execuție** (tool-uri deterministe, testabile unitar). Niciun agent LLM nu scrie direct în sistem — orice scriere trece prin tool-uri deterministe, iar orice acțiune cu risc peste prag trece printr-o poartă de aprobare umană.

## 1. Retriever agent

**Responsabilitate**: aduce context istoric relevant pentru incidentul curent, cu trasabilitate completă la sursă.

| | |
|---|---|
| **Input** | Descrierea incidentului curent (text) + metadate opționale (categorie, sistem afectat) pentru filtrare |
| **Output** | Listă structurată de incidente similare: `incident_id`, `data`, `scor_similaritate`, `rezumat` |
| **Tehnologie** | Embeddings (`sentence-transformers` sau embeddings Ollama) + ChromaDB |
| **LLM implicat** | Nu |

**Tool-uri**
- `embed_query(text) -> vector` — transformă incidentul curent în embedding, folosind același model ca la indexare
- `search_similar_incidents(vector, k=5, filters=None) -> list[IncidentMatch]` — interogare ChromaDB, top-k după similaritate cosine

**Reguli de implementare**
- Fiecare incident din setul mock e indexat cu metadata atașată (`incident_id`, `data`, `categorie`, `severitate`), nu doar text brut — permite filtrare înainte de similarity search
- Prag minim de similaritate (ex: sub 0.6 = irelevant) — stabilit și justificat explicit, nu implicit
- ID-ul original al fiecărui incident e păstrat integral prin tot fluxul — orice ipoteză de mai târziu trebuie să poată fi trasată înapoi la `incident_id`-urile care au fundamentat-o

**Ce NU face**: nu interpretează, nu decide cauze, nu generează text nou — mecanism de căutare, atât.

---

## 2. Analyst agent (Chain-of-Thought)

**Responsabilitate**: singurul punct din sistem unde se face raționament — transformă context istoric + incident curent în ipoteze de cauză motivate.

| | |
|---|---|
| **Input** | Incidentul curent + lista de incidente similare (din Retriever), formatate în prompt structurat |
| **Output** | JSON strict, validat cu Pydantic |
| **Tehnologie** | LLM open-source (Ollama local sau Groq free tier) |
| **LLM implicat** | Da — singurul agent care generează text liber/raționament |

**Schema de output (Pydantic)**

```python
class Hypothesis(BaseModel):
    cauza_probabila: str
    incredere: float  # 0.0-1.0
    incidente_citate: list[str]  # ID-uri, nu texte libere
    severitate_estimata: Literal["Low", "Medium", "High", "Critical"]
    rationament: str  # rezumat CoT, nu tot raționamentul brut

class AnalystOutput(BaseModel):
    incident_id: str
    ipoteze: list[Hypothesis]  # de regulă 1-3, ordonate după incredere
```

**Reguli de implementare**
- Promptul cere explicit raționament pas-cu-pas *înainte* de JSON-ul final ("gândește-te ce au în comun incidentele similare, apoi formulează ipoteza") — raționamentul brut se loghează separat (util pentru Phoenix), fără să polueze schema de output
- Dacă parsing-ul JSON eșuează sau validarea Pydantic pică → retry cu eroarea inclusă în prompt ("output-ul nu respectă schema, eroarea a fost X"). Niciun JSON malformat nu trece mai departe în flux
- `incidente_citate` trebuie să conțină exclusiv ID-uri care au apărut efectiv în contextul furnizat de Retriever — verificat printr-un check programatic suplimentar (nu doar Pydantic), pentru a preveni citări halucinate

**Ce NU face**: nu scrie nimic persistent, nu decide dacă se execută ceva — doar propune.

---

## 3. Problem Record Builder

**Responsabilitate**: transformă output-ul validat al Analyst-ului în recordul final, aplicând reguli de business deterministe. Aici se concretizează separarea reasoning/execuție.

| | |
|---|---|
| **Input** | `AnalystOutput` (deja validat Pydantic) |
| **Output** | `ProblemRecord` — obiectul final pregătit pentru scriere în sistem |
| **Tehnologie** | Logică Python pură, fără LLM |
| **LLM implicat** | Nu |

**Reguli de business (exemple)**
- Dacă `severitate_estimata == "Critical"` ȘI `incredere < 0.5` → se forțează `severitate_finala = "High"` (regulă de precauție codificată explicit, nu decisă de model)
- Maparea pe categorie ITIL: dicționar cuvinte-cheie → categorie, nu inferență liberă
- Calculează `necesita_aprobare: bool` pe baza pragurilor definite — acesta e semnalul pentru Approval gate

**Reguli de implementare**
- Funcție pură, testabilă unitar clasic: dai un `AnalystOutput` mock, verifici că output-ul e cel așteptat — demonstrează direct separarea reasoning/execuție cerută
- Nicio interpretare de text liber, niciun apel LLM

**Ce NU face**: nu interpretează, nu regenerează, nu apelează din nou modelul.

---

## 4. Approval gate

**Responsabilitate**: punct de control uman — oprește fluxul înainte de orice scriere/execuție cu impact, dacă pragul de risc e depășit.

| | |
|---|---|
| **Input** | `ProblemRecord` + flagul `necesita_aprobare` |
| **Output** | Continuă automat (sub prag) sau intră în așteptare pentru decizie umană (aprobat/respins/modificat) |
| **Tehnologie** | State machine / `interrupt()` (LangGraph) sau echivalent |
| **LLM implicat** | Nu |

**Praguri (exemplu, de justificat explicit în document)**
- `severitate_finala >= "High"` → necesită aprobare (o escaladare greșită la acest nivel afectează SLA-uri active)
- Propunere de închidere/escaladare automată a unui incident cu impact major → necesită aprobare

**Reguli de implementare**
- Punct natural pentru `interrupt()` dacă orchestrarea e făcută cu LangGraph — graful se oprește, salvează state-ul, așteaptă input extern (ex: buton „Aprobă"/„Respinge" în interfața Streamlit)
- Fiecare decizie umană (cine, când, ce a ales) e logată integral — alimentează direct cerința de audit (cine a aprobat, pe ce bază)
- O respingere poate întoarce fluxul la Analyst agent cu feedback („aprobatorul a respins pentru că...") în loc să oprească definitiv — opțional, dar arată maturitate de design

**Ce NU face**: nu decide singur — garantează că nimic riscant nu trece fără om în buclă.
