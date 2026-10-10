# mcp-guap

MCP-сервер для личного кабинета ГУАП ([pro.guap.ru](https://pro.guap.ru)).
Позволяет ИИ-агентам (Claude и другим) работать с заданиями, материалами и отчётами студента.

## Что умеет

### MCP Mode (для ИИ-ассистентов)

| Инструмент | Описание |
|---|---|
| `authenticate` | 🔐 Авторизация через браузер (открывает окно, ждёт входа, сохраняет cookies) |
| `check_auth_status` | Проверить, валидны ли сохранённые cookies |
| `list_tasks` | Список всех заданий текущего семестра (дедлайны, баллы, статусы) |
| `get_task` | Детали задания: описание, доп. материалы, сданные отчёты |
| `list_materials` | Учебные материалы семестра (файлы и внешние ссылки) |
| `download_material` | Скачать учебный материал (с pro.guap.ru, Google Drive или любой ссылке) |
| `submit_report` | Загрузить файл отчёта к заданию |
| `get_my_profile` | Профиль студента: ФИО, группа, номер зачётки |
| `get_teacher_info` | Информация о преподавателе |
| `get_subject_info` | Информация о дисциплине |
| `get_my_group_order` | Порядковый номер в группе |

### CLI Mode (автономный терминал)

| Команда | Описание |
|---|---|
| `guap pro auth` | 🔐 Авторизация через браузер |
| `guap pro check` | Проверить авторизацию |
| `guap pro tasks` | Список заданий с фильтрами |
| `guap pro task <id>` | Детали задания |
| `guap pro materials` | Учебные материалы |
| `guap pro profile` | Профиль студента |
| `guap skill` | Установить Agent Skill в `agents/skills/` |

## Требования

- [uv](https://docs.astral.sh/uv/getting-started/installation/) — менеджер пакетов Python
- [Claude Desktop](https://claude.ai/download) (или любой другой MCP-клиент)
- Аккаунт ГУАП на [pro.guap.ru](https://pro.guap.ru)

## Установка

Клонировать репозиторий не нужно — достаточно `uv`.

### Вариант 1: Автоматическая авторизация (рекомендуется)

**1. Установить Playwright browsers**

При первом запуске автоматической авторизации, Claude установит необходимые браузеры автоматически. Это может занять 1-2 минуты.

Или установите вручную:
```bash
uvx playwright install chromium
```

**2. Добавить сервер в Claude Desktop**

Откройте файл конфигурации Claude Desktop:
- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
- **Linux**: `~/.config/Claude/claude_desktop_config.json`

Добавьте секцию `mcpServers`:

```json
{
  "mcpServers": {
    "guap": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/ehlvg/mcp-guap", "mcp-guap"]
    }
  }
}
```

**2. Перезапустить Claude Desktop**

**3. Выполнить авторизацию**

Просто скажите Claude:
> "Выполни авторизацию в ГУАП"

Claude откроет браузер, вам нужно будет ввести логин и пароль. Cookies сохранятся автоматически.

MCP сохраняет cookies кабинета и SSO с привязкой к домену и пути. Если сессия кабинета истекла, но SSO ещё действует, запрос проходит обычные перенаправления авторизации и сохраняет обновлённые cookies. Когда истечёт и SSO-сессия, потребуется повторный вход через `authenticate`.

### Вариант 2: Ручная настройка (без браузера)

Если не хотите использовать автоматическую авторизацию:

1. Войдите в [pro.guap.ru](https://pro.guap.ru) в браузере
2. Откройте DevTools → вкладка **Network**
3. Обновите страницу, кликните на любой запрос к `pro.guap.ru`
4. В заголовках запроса найдите **Cookie** и скопируйте всё значение
5. Добавьте в конфигурацию Claude Desktop:

```json
{
  "mcpServers": {
    "guap": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/ehlvg/mcp-guap", "mcp-guap"],
      "env": {
        "GUAP_COOKIE": "YOUR_COOKIE_STRING_HERE"
      }
    }
  }
}
```

> Куки живут несколько часов. Когда перестанет работать — выполните `authenticate` снова или обновите `GUAP_COOKIE`.

### Вариант 3: Agent Skill (для AI-агентов с поддержкой Agent Skills)

Если ваш AI-агент поддерживает [Agent Skills](https://agentskills.io/):

```bash
# Установить skill в agents/skills/
uvx --from git+https://github.com/ehlvg/mcp-guap guap skill

# Или в кастомную директорию
uvx --from git+https://github.com/ehlvg/mcp-guap guap skill --path ./my-agents/skills
```

Skill будет автоматически обнаружен агентом. Просто спросите:
> "Помоги мне с заданиями в ГУАП"

### Вариант 4: CLI режим (терминал)

Если предпочитаете работать в терминале:

```bash
# Использование
uvx --from git+https://github.com/ehlvg/mcp-guap guap pro auth
guap pro tasks
guap pro task 181395
guap pro materials
guap pro profile
```

#### Форматы вывода

Поддерживаются форматы `table` (по умолчанию), `json` и `csv`:

```bash
# JSON формат
guap pro tasks --format json
guap pro profile --format json
guap pro task 181395 --format json

# CSV формат
guap pro tasks --format csv > tasks.csv
guap pro materials --format csv > materials.csv
```

## Использование

### MCP режим

Просто общайтесь с Claude на естественном языке:

> «Покажи все мои задания»
> «Что нужно сдать по вычислительной математике?»
> «Загрузи файл ~/Documents/report.pdf как отчёт к заданию 181395»

## Запуск вручную (для отладки)

```bash
GUAP_COOKIE="..." uvx --from git+https://github.com/ehlvg/mcp-guap mcp-guap
```

## Структура проекта

```
mcp-guap/
├── mcp_guap/
│   ├── server.py        # MCP-сервер
│   ├── cli.py           # CLI инструмент (guap)
│   ├── auth.py          # Авторизация через браузер
│   ├── guap_client.py   # HTTP-клиент
│   └── skill/           # Agent Skill (agentskills.io)
│       ├── SKILL.md     # Skill metadata + instructions
│       ├── scripts/     # Helper scripts
│       └── references/  # Documentation
├── pyproject.toml       # Зависимости проекта
└── cookie.json          # Cookies (автосоздается)
```
