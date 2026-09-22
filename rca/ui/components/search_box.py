"""A search field that narrows the list while the person types.

Streamlit sends the text of a field to the application only once it is committed — Enter,
or leaving the field — so a plain search would filter only after Enter, which is not how a
search behaves. The field itself is the ordinary `st.text_input`, with its own key, its own
value and its own look; the small script below asks the browser to commit what has been
typed shortly after the typing stops, and the list follows from there.

The pause is there on purpose: it keeps one rerun per word rather than one per keystroke.
"""

import streamlit as st

PAUSE_MS = 200

_LIVE_TYPING = """
<script>
(function () {
  const doc = window.parent.document;
  let timer = null;

  function attach() {
    const input = doc.querySelector(".st-key-__KEY__ input");
    if (!input || input.dataset.liveSearch === "1") { return; }
    input.dataset.liveSearch = "1";
    input.addEventListener("input", function () {
      clearTimeout(timer);
      timer = setTimeout(function () {
        input.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
      }, __PAUSE__);
    });
  }

  attach();
  // The field is redrawn on every rerun, so the script waits for each new one.
  new MutationObserver(attach).observe(doc.body, { childList: true, subtree: true });
})();
</script>
"""


def filter_while_typing(key: str) -> None:
    """Make the field with this key commit what is typed, without waiting for Enter.

    The script has to live somewhere on the page, so it is kept in a container the theme
    folds away: it has nothing to show, and it takes no room beside the field either.
    """
    with st.container(key=f"live-search-{key}", width="content"):
        st.iframe(
            _LIVE_TYPING.replace("__KEY__", key).replace("__PAUSE__", str(PAUSE_MS)),
            height=1,
            width="content",
        )


def search_field(label: str, *, key: str, placeholder: str, hide_label: bool = False) -> None:
    """The search field itself: the ordinary one, nothing added to the row it sits in.

    The script that makes it filter while typing is placed by `filter_while_typing`, after
    the row is closed, so that the field keeps the width it would have on its own.
    """
    st.text_input(
        label,
        placeholder=placeholder,
        key=key,
        icon=":material/search:",
        width="stretch",
        label_visibility="collapsed" if hide_label else "visible",
    )
