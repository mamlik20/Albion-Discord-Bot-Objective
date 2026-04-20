import discord
from discord import app_commands
import logging
import json
import io
from PIL import Image
from .add_data import _internal_add_item
from utils.gemini_manager import gemini_manager


@app_commands.command(
    name="add_from_image",
    description="Добавляет объект, распознав данные и тип с изображения (через Gemini)."
)
@app_commands.describe(image="Изображение (скриншот) с данными об объекте")
async def add_from_image(interaction: discord.Interaction, image: discord.Attachment):
    if not gemini_manager.is_configured:
        await interaction.response.send_message(
            "Ошибка: API для Gemini не сконфигурирован (нет GOOGLE_API_KEY).",
            ephemeral=True
        )
        return

    if not image.content_type or not image.content_type.startswith("image/"):
        await interaction.response.send_message(
            "Ошибка: Прикрепленный файл не является изображением.",
            ephemeral=True
        )
        return

    await interaction.response.defer(ephemeral=True, thinking=True)

    try:
        image_bytes = await image.read()
        img = Image.open(io.BytesIO(image_bytes))

        prompt = """
        Ты — эксперт по анализу игровых скриншотов из игры Albion Online. Твоя задача — извлечь из изображения данные об объекте и классифицировать его.

        КЛАССИФИКАЦИЯ ОБЪЕКТОВ:
        1. Если в названии есть слова типа:
           - "волокн(о|а)" или "fiber" -> тип "Ткань"
           - "шкур(а|ы)" или "skin" -> тип "Кожа" 
           - "руд(а|ы)" или "ore" -> тип "Руда"
           - "древесин(а|ы)" или "wood" -> тип "Дерево"
           - "вихр(ь|я)" или "vortex" -> тип "Вихрь"
           - "сил(ы,а) или "anomaly" -> тип "Сфера"
        
        2. Для объектов с тировыми обозначениями (Tier 8.4, T8.4, Bolca 8. kademe 4 и т.п.):
           - Добавь префикс тира к типу: "8.4 Ткань", "8.4 Руда" и т.д.

        3. Для "Вихрь" - ОПРЕДЕЛЕНИЕ ЦВЕТА:
           Силовой вихрь выглядит как КРИСТАЛЛ с вращающимися лентами/полосками вокруг.
           Определи ЦВЕТ КРИСТАЛЛА (не лент!):
           - ЖЕЛТЫЙ или ЗОЛОТОЙ кристалл -> "Золотой вихрь"
           - ФИОЛЕТОВЫЙ кристалл -> "Фиолетовый вихрь"  
           - СИНИЙ кристалл -> "Синий вихрь"
           - ЗЕЛЕНЫЙ кристалл -> "Зеленый вихрь"
        
        4. Для сфера - ОПРЕДЕЛЕНИЕ ЦВЕТА:
           Аномамалия силы выглядит как СФЕРА определёного цвета.
           Определи ЦВЕТ СФЕРЫ:
           - ЖЕЛТЫЙ или ЗОЛОТОЙ сфера -> "Золотая сфера"
           - ФИОЛЕТОВЫЙ сфера -> "Фиолетовая сфера"  
           - СИНИЙ сфера -> "Синняя сфера"
           - ЗЕЛЕНЫЙ сфера -> "Зеленая сфера"

        ИЗВЛЕКАЕМЫЕ ДАННЫЕ:
        1. 'location': Название локации (оставь как есть)
        2. 'object_type': Классифицированный тип объекта (см. правила выше)
        3. 'time_str': Время до появления объекта в формате "Чч Мм Сс" на русском.

        Верни ТОЛЬКО JSON:
        {
          "location": "название локации",
          "object_type": "классифицированный тип",
          "time_str": "время"
        }
        """

        response = await interaction.client.loop.run_in_executor(
            None,
            lambda: gemini_manager.generate_with_fallback(
                model_name='gemini-2.5-flash',
                contents=[prompt, img],
                generation_config={"temperature": 0.0}
            )
        )

        response_content = response.text
        logging.info(f"Ответ от Gemini: {response_content}")

        clean_json = response_content.replace('```json', '').replace('```', '').strip()

        try:
            api_data = json.loads(clean_json)
            location = api_data.get("location")
            object_type = api_data.get("object_type")
            time_str = api_data.get("time_str")

            if not all([location, object_type, time_str]):
                await interaction.followup.send(
                    f"Не удалось распознать все данные. Ответ нейросети:\n`{clean_json}`",
                    ephemeral=True
                )
                return

            error_message = await _internal_add_item(interaction, str(time_str), location, object_type)

            if error_message:
                await interaction.followup.send(error_message, ephemeral=True)
            else:
                await interaction.followup.send(
                    f"✅ **Распознано и добавлено:**\n"
                    f"**Тип:** {object_type}\n"
                    f"**Локация:** {location}\n"
                    f"**Время:** {time_str}",
                    ephemeral=True
                )

        except json.JSONDecodeError as e:
            logging.error(f"Ошибка парсинга JSON: {e}. Контент: {response_content}")
            await interaction.followup.send(
                f"Ошибка: Не удалось обработать формат ответа. Контент: `{response_content[:100]}`",
                ephemeral=True
            )

    except RuntimeError as e:
        logging.error(f"Все ключи Gemini исчерпаны: {e}")
        await interaction.followup.send(
            "⚠️ Все ключи исчерпали лимиты. Попробуйте позже.",
            ephemeral=True
        )

    except Exception as e:
        logging.error(f"Ошибка в команде add_from_image: {e}", exc_info=True)
        await interaction.followup.send(
            f"Произошла ошибка при обращении к Gemini: {str(e)}",
            ephemeral=True
        )
