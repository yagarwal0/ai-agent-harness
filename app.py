"""Run with: python -m streamlit run app.py"""

import streamlit as st

from tutor.config import Config
from tutor.harness import TutorSession
from tutor.openai_model import OpenAIModel
from tutor.pdf_export import build_pdf
from tutor.schemas import SCORING_RUBRIC
from tutor.sources import load_source
from tutor.search import BraveSearch


st.set_page_config(page_title="Interview Tutor", page_icon=":question:", layout="centered")
st.title("Interview Tutor")
config = Config()
session = st.session_state.get("session")
if session is not None and (
    not hasattr(session, "answers") or not hasattr(session, "search_calls")
    or getattr(getattr(session, "model", None), "name", None) != config.model
):
    st.info("The interview format has changed. Start a new session to use URL/topic questions.")
    if st.button("New session"):
        st.session_state.pop("session", None)
        st.session_state.pop("pdf_bytes", None)
        st.rerun()
    st.stop()

if session is None:
    with st.form("start"):
        url = st.text_input("Full page URL (optional)", placeholder="https://en.wikipedia.org/wiki/Supervised_learning", max_chars=2048, key="source_url")
        topic = st.text_input("Topic or focus (optional)", placeholder="Supervised learning, unsupervised learning, two pointers...", max_chars=160, key="topic")
        st.caption("Use a URL, a topic, or both. The app reads one public page and does not follow its links.")
        with st.expander("Paste source text instead"):
            pasted = st.text_area("Problem statement or page text", max_chars=config.max_problem_chars,
                                  help="Use this if the page needs login, blocks retrieval, or relies on JavaScript. Pasted text replaces page fetching.")
        level = st.selectbox("Practice level", ["Beginner", "Intermediate", "Advanced"])
        company = st.text_input("Target company or tier (optional)", max_chars=100)
        submitted = st.form_submit_button("Start interview")
    if submitted:
        try:
            with st.spinner("Reading your source..."):
                source = load_source(url, topic, pasted, max_chars=config.max_source_chars)
            material = (("Source excerpt is truncated; the full page was not read.\n" if source.truncated else "") + source.text)
            model = OpenAIModel(config.model)
            session = TutorSession(material, level, company, model, config,
                                   source_url=source.source_url, source_title=source.title,
                                   search_client=BraveSearch() if config.max_search_calls > 0 else None)
            st.session_state.session = session
            try:
                with st.spinner("Preparing your questions..."):
                    session.start()
            except ValueError as error:
                session.notice = str(error)
            st.rerun()
        except ValueError as error:
            st.error(str(error))
        except Exception:
            st.error("Could not start the interview. Check your API key, connection, and model settings.")
else:
    st.caption(f"{session.level} | {session.status}")
    with st.expander("Source material"):
        st.write(session.source_title)
        if session.source_url:
            st.text(session.source_url)
        st.text(session.problem)
    if session.research_sources:
        with st.expander("Extra context sources"):
            st.caption("Search snippets were used for context; linked pages were not automatically opened.")
            for source in session.research_sources:
                st.write(source["title"])
                st.text(source["url"])
    if session.notice:
        st.warning(session.notice)
    for message in session.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
    if session.status == "Interviewing":
        if text := st.chat_input("Answer the current question (include code if relevant)", max_chars=config.max_message_chars):
            try:
                with st.spinner("Reviewing your answers..." if len(session.answers) + 1 == session.question_count else "Saving your answer..."):
                    session.send(text)
            except ValueError as error:
                session.notice = str(error)
            st.rerun()
        st.caption("You can finish at any time to receive your marks and revision PDF.")
        if st.button("Finish & prepare PDF"):
            with st.spinner("Reviewing your answers..."):
                session.finish()
            st.rerun()
    else:
        st.subheader("Your interview marks")
        assessment = session.notes.assessment if session.notes else None
        st.caption("AI feedback on this session, not a hiring-readiness prediction. Code is never executed.")
        if assessment is not None:
            if assessment.total is not None:
                st.metric("Review score", f"{assessment.total}/10")
            else:
                st.info("Partial review: an overall score needs evidence for every criterion.")
            for field, label, maximum in SCORING_RUBRIC:
                item = getattr(assessment, field)
                marks = "Not assessed" if item.marks is None else f"{item.marks}/{maximum}"
                st.markdown(f"**{label}: {marks}**")
                st.write(item.reason)
                if item.marks is not None:
                    st.text(f"Evidence: {item.evidence}")
            st.markdown("**How to improve**")
            for improvement in assessment.improvements:
                st.write(f"- {improvement}")
        else:
            st.info(session.assessment_notice or "Not assessed: no valid review is available.")
        if "pdf_bytes" not in st.session_state:
            try:
                st.session_state.pdf_bytes = build_pdf(
                    session.problem, session.level, session.company, session.messages,
                    session.notes, status=session.status, model_name=session.model.name,
                    source_url=session.source_url, source_title=session.source_title,
                    question_count=session.question_count, answered_count=len(session.answers),
                    assessment_notice=session.assessment_notice,
                    research_sources=session.research_sources,
                )
            except Exception:
                st.error("PDF export failed. Your session is retained; rerun to retry.")
        if "pdf_bytes" in st.session_state:
            st.download_button("Download revision PDF", st.session_state.pdf_bytes,
                               file_name="interview-tutor-notes.pdf", mime="application/pdf")
    st.caption(
        f"Model calls: {session.calls} | Searches: {session.search_calls} | "
        f"Tokens reported: {session.input_tokens} in / {session.output_tokens} out | "
        f"Estimated cost: ${session.estimated_cost:.4f}"
        + (" (some usage unknown)" if session.usage_unknown else "")
    )
    if st.button("New session"):
        st.session_state.pop("session", None)
        st.session_state.pop("pdf_bytes", None)
        st.rerun()
