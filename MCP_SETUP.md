# Инструкция по настройке ThaiMCP сервера в Cursor

## Способ 1: Через настройки Cursor (UI)

1. Откройте Cursor
2. Нажмите `Ctrl + Shift + P` (или `F1`) для открытия Command Palette
3. Введите: `MCP` или `Preferences: Open User Settings (JSON)`
4. Найдите раздел MCP Servers в настройках
5. Добавьте следующую конфигурацию:

```json
{
  "mcpServers": {
    "ThaiCustomsMCP": {
      "command": "python",
      "args": [
        "C:\\Users\\User\\PycharmProjects\\PythonProject52_Thai_MCP_Server\\server.py"
      ]
    }
  }
}
```

## Способ 2: Через файл настроек напрямую

1. Откройте файл настроек Cursor:
   - Нажмите `Ctrl + Shift + P`
   - Введите: `Preferences: Open User Settings (JSON)`
   - Или откройте файл: `%APPDATA%\Cursor\User\settings.json`

2. Добавьте в файл `settings.json` секцию:

```json
{
  "mcpServers": {
    "ThaiCustomsMCP": {
      "command": "python",
      "args": [
        "C:\\Users\\User\\PycharmProjects\\PythonProject52_Thai_MCP_Server\\server.py"
      ],
      "env": {
        "OPENAI_API_KEY": "ваш_ключ_если_нужен"
      }
    }
  }
}
```

## Способ 3: Через Command Palette

1. Нажмите `Ctrl + Shift + P`
2. Введите: `/mcp` или `MCP: Add Server`
3. Следуйте инструкциям мастера настройки

## Проверка работы

После настройки:
1. Перезапустите Cursor
2. В чате с AI попробуйте использовать инструменты:
   - `ping` - для проверки подключения
   - `list_demo_parts` - для получения списка демо-запчастей
   - `classify_auto_part` - для классификации автозапчасти
   - `draft_thai_declaration` - для создания таможенной декларации

## Примечания

- Убедитесь, что Python установлен и доступен из командной строки
- Если используете виртуальное окружение, укажите полный путь к `python.exe` из venv
- Для работы с OpenAI API (необязательно) установите переменную окружения `OPENAI_API_KEY`


