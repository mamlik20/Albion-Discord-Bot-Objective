# utils/gemini_manager.py
"""
Добавь ключи в .env через запятую:
GOOGLE_API_KEY=key1,key2,key3
"""

import os
import logging
import google.generativeai as genai
from google.api_core.exceptions import ResourceExhausted, TooManyRequests

PROXY_URL = os.getenv("PROXY_URL", "http://xray:10809")
os.environ["HTTP_PROXY"] = PROXY_URL
os.environ["HTTPS_PROXY"] = PROXY_URL
os.environ["grpc_proxy"] = PROXY_URL


class GeminiKeyManager:
    """
    Хранит список API-ключей и переключает на следующий,
    когда текущий возвращает ошибку превышения лимита (429 / ResourceExhausted).
    """

    def __init__(self):
        raw = os.getenv("GOOGLE_API_KEY", "")
        self.keys = [k.strip() for k in raw.split(",") if k.strip()]
        self.current_index = 0

        if not self.keys:
            logging.error("GeminiKeyManager: GOOGLE_API_KEY не задан в .env!")
        else:
            logging.info(f"GeminiKeyManager: загружено {len(self.keys)} ключ(ей).")
            self._apply_current_key()

    @property
    def is_configured(self) -> bool:
        return bool(self.keys)

    def _apply_current_key(self):
        """Применяет текущий ключ к genai."""
        key = self.keys[self.current_index]
        genai.configure(api_key=key)
        logging.info(f"GeminiKeyManager: активен ключ #{self.current_index + 1} (…{key[-6:]})")

    def rotate(self) -> bool:
        """
        Переключается на следующий ключ.
        Возвращает True, если переключение удалось (есть ещё ключи),
        False — если все ключи исчерпаны (прошли полный круг).
        """
        next_index = (self.current_index + 1) % len(self.keys)

        if next_index == self.current_index:
            logging.warning("GeminiKeyManager: только один ключ, ротация невозможна.")
            return False

        self.current_index = next_index
        self._apply_current_key()
        return True

    def generate_with_fallback(self, model_name: str, contents, generation_config=None):
        if not self.is_configured:
            raise RuntimeError("Gemini API не сконфигурирован — нет ни одного ключа.")

        tried_keys = set()
        total_keys = len(self.keys)

        while len(tried_keys) < total_keys:
            tried_keys.add(self.current_index)
            try:
                model = genai.GenerativeModel(model_name)
                response = model.generate_content(
                    contents,
                    generation_config=generation_config or {}
                )
                return response

            except (ResourceExhausted, TooManyRequests) as e:
                logging.warning(
                    f"GeminiKeyManager: ключ #{self.current_index + 1} исчерпан (429). "
                    f"Пробуем следующий... [{len(tried_keys)}/{total_keys}]"
                )
                rotated = self.rotate()
                if not rotated or self.current_index in tried_keys:
                    raise RuntimeError(
                        f"Все {total_keys} ключей Gemini исчерпали лимиты. "
                        "Добавьте новые ключи в GOOGLE_API_KEY."
                    ) from e

            except Exception as e:
                raise

gemini_manager = GeminiKeyManager()
