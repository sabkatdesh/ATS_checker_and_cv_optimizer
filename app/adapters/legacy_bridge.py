"""Temporary bridge to the legacy modules (deleted in Task 10).

Every legacy import happens inside a method so nothing legacy loads at import time.
"""

import importlib
from typing import Any

from app.ports.auth import InvalidToken
from app.ports.llm_legacy import StructuredLLM
from app.ports.rendering import CoverLetterRenderer, CvPdfRenderer

JsonDict = dict[str, Any]


class LegacyModuleStore:
    def _db(self) -> Any:
        return importlib.import_module("database")

    def get_cv_profile(self, user_id: str) -> JsonDict | None:
        return self._db().get_cv_profile(user_id)

    def save_cv_profile(self, user_id: str, data: JsonDict) -> Any:
        return self._db().save_cv_profile(user_id, data)

    def create_session(
        self,
        user_id: str,
        thread_id: str,
        job_description: str,
        template_id: str = "classic",
        domain: str | None = None,
        cover_letter_requested: bool = False,
        cover_letter_tone: str | None = None,
        cover_letter_length: str | None = None,
    ) -> JsonDict:
        return self._db().create_session(
            user_id,
            thread_id,
            job_description,
            template_id=template_id,
            domain=domain,
            cover_letter_requested=cover_letter_requested,
            cover_letter_tone=cover_letter_tone,
            cover_letter_length=cover_letter_length,
        )

    def update_session(self, thread_id: str, updates: JsonDict) -> None:
        self._db().update_session(thread_id, updates)

    def get_session(self, thread_id: str) -> JsonDict | None:
        return self._db().get_session(thread_id)

    def get_user_sessions(self, user_id: str) -> list[JsonDict]:
        return self._db().get_user_sessions(user_id)

    def upload_pdf_to_storage(self, thread_id: str, user_id: str, local_path: str) -> str:
        return self._db().upload_pdf_to_storage(thread_id, user_id, local_path)

    def get_cv_templates(self) -> list[JsonDict]:
        return self._db().get_cv_templates()

    def get_user_settings(self, user_id: str) -> JsonDict | None:
        return self._db().get_user_settings(user_id)

    def save_user_settings(self, user_id: str, data: JsonDict) -> Any:
        return self._db().save_user_settings(user_id, data)

    def get_coin_balance(self, user_id: str) -> int:
        return self._db().get_coin_balance(user_id)

    def deduct_coins(self, user_id: str, amount: int, description: str) -> bool:
        return self._db().deduct_coins(user_id, amount, description)

    def add_coins(self, user_id: str, amount: int, description: str) -> None:
        self._db().add_coins(user_id, amount, description)

    def get_coin_transactions(self, user_id: str) -> list[JsonDict]:
        return self._db().get_coin_transactions(user_id)


class LegacyTokenVerifier:
    def user_id_for(self, token: str) -> str:
        try:
            db = importlib.import_module("database")
            return str(db.supabase.auth.get_user(token).user.id)
        except Exception as exc:
            raise InvalidToken("invalid token") from exc


class LegacyPipeline:
    def _graph(self) -> Any:
        return importlib.import_module("core.pipeline.graph")

    def run(
        self,
        *,
        job_description: str,
        user_resume_text: str,
        thread_id: str,
        cover_letter_requested: bool = False,
        cover_letter_tone: str | None = None,
        cover_letter_length: str | None = None,
    ) -> JsonDict:
        return self._graph().run_pipeline_for_user(
            job_description=job_description,
            user_resume_text=user_resume_text,
            thread_id=thread_id,
            cover_letter_requested=cover_letter_requested,
            cover_letter_tone=cover_letter_tone,
            cover_letter_length=cover_letter_length,
        )

    def get_state(self, thread_id: str) -> JsonDict:
        return self._graph().get_pipeline_state(thread_id)

    def resume(self, thread_id: str, user_qna: str) -> JsonDict:
        return self._graph().resume_pipeline_for_user(thread_id, user_qna)

    def resume_cover_letter(self, thread_id: str, tone: str, length: str) -> JsonDict:
        return self._graph().resume_cover_letter_for_user(thread_id, tone, length)


def legacy_llm() -> StructuredLLM:
    return importlib.import_module("core.llm_client").AzureLLMClient()


def legacy_pdf() -> CvPdfRenderer:
    return importlib.import_module("services.pdf_generator").PDFGenerator()


def legacy_cover_letter() -> CoverLetterRenderer:
    return importlib.import_module("services.cover_letter").CoverLetterService()
