"""HTTP client and HTML parsers for pro.guap.ru"""

import re
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import httpx
from bs4 import BeautifulSoup

try:
    from .session_cookies import SessionCookies, from_header
except ImportError:
    from session_cookies import SessionCookies, from_header

BASE_URL = "https://pro.guap.ru"


@dataclass
class Task:
    task_id: int
    discipline: str
    discipline_id: Optional[int]
    name: str
    status: Optional[str]
    points_earned: Optional[str]
    points_max: Optional[str]
    task_type: str
    deadline: Optional[str]
    updated_at: str
    teacher: str
    teacher_id: Optional[int]


@dataclass
class TaskDetail:
    task_id: int
    name: str
    discipline: str
    discipline_id: Optional[int]
    task_type: str
    semester: str
    teacher: str
    teacher_id: Optional[int]
    points_max: Optional[str]
    order_num: Optional[str]
    added_at: Optional[str]
    allowed_extensions: str
    deadline: Optional[str]
    description: str
    extra_materials: list[dict]
    reports: list[dict]
    csrf_token: str


@dataclass
class Material:
    download_url: str
    external_url: Optional[str]
    discipline: str
    discipline_id: Optional[int]
    name: str
    added_at: str
    teacher: str
    teacher_id: Optional[int]


@dataclass
class Profile:
    full_name: str
    group: str
    student_id: str
    institute: Optional[str]
    specialty: Optional[str]
    direction: Optional[str]
    study_form: Optional[str]
    education_level: Optional[str]
    status: Optional[str]


@dataclass
class TeacherProfile:
    teacher_id: int
    full_name: str
    degree: Optional[str]
    positions: list[dict]


@dataclass
class SubjectDetail:
    subject_id: int
    name: str
    department: Optional[str]
    year_semester: Optional[str]
    control_type: Optional[str]
    grade: Optional[str]
    hours: Optional[str]
    teacher: Optional[str]
    teacher_id: Optional[int]
    teacher_position: Optional[str]
    lesson_types: Optional[str]
    groups: Optional[str]


def _href_id(href: Optional[str], prefix: str) -> Optional[int]:
    if not href:
        return None
    m = re.search(rf"{re.escape(prefix)}(\d+)", href)
    return int(m.group(1)) if m else None


@contextmanager
def _make_client(cookie: str | SessionCookies, transport: httpx.BaseTransport | None = None):
    session = from_header(cookie) if isinstance(cookie, str) else cookie
    with httpx.Client(
        base_url=BASE_URL,
        cookies=session.cookies,
        headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"},
        follow_redirects=True,
        timeout=30,
        transport=transport,
    ) as client:
        try:
            yield client
        finally:
            session.save(client.cookies)


def get_tasks(
    cookie: str,
    semester: Optional[int] = None,
    subject: Optional[int] = None,
    task_type: Optional[int] = None,
    show_status: Optional[int] = None,
) -> list[Task]:
    """Fetch all tasks for the given (or default current) semester with optional filters."""
    params: dict = {}
    if semester is not None:
        params["semester"] = semester
    if subject is not None:
        params["subject"] = subject
    if task_type is not None:
        params["type"] = task_type
    if show_status is not None:
        params["showStatus"] = show_status

    with _make_client(cookie) as client:
        r = client.get("/inside/student/tasks/", params=params)
        r.raise_for_status()

    soup = BeautifulSoup(r.text, "lxml")

    # Find semester value from the selected option if not supplied
    if semester is None:
        sel = soup.select_one("select[name='semester'] option[selected]")
        if not sel:
            # first semester option
            sel = soup.select_one("select[name='semester'] option")

    tasks: list[Task] = []
    table = soup.select_one("table")
    if not table:
        return tasks

    for row in table.select("tr"):
        cells = row.select("td, th")
        if not cells or cells[0].name == "th":
            continue
        # Layout (10 columns):
        # 0: icon+link  1: Дисциплина  2: №в сем  3: Название  4: Статус
        # 5: Баллы  6: Тип  7: Предельная дата  8: Дата изменения  9: Преподаватель
        tds = row.select("td")
        if len(tds) < 4:
            continue

        task_link = tds[0].select_one("a")
        task_id_val = _href_id(task_link["href"] if task_link else None, "/inside/student/tasks/")

        disc_link = tds[1].select_one("a")
        discipline = disc_link.get_text(strip=True) if disc_link else ""
        discipline_id = _href_id(disc_link["href"] if disc_link else None, "/inside/students/subjects/")

        # tds[2] = № в сем (ignored)
        name_link = tds[3].select_one("a") if len(tds) > 3 else None
        name = name_link.get_text(strip=True) if name_link else (tds[3].get_text(strip=True) if len(tds) > 3 else "")

        status = tds[4].get_text(strip=True) or None if len(tds) > 4 else None
        points_raw = tds[5].get_text(strip=True) if len(tds) > 5 else ""
        task_type = tds[6].get_text(strip=True) if len(tds) > 6 else ""
        deadline = tds[7].get_text(strip=True) or None if len(tds) > 7 else None
        updated_at = tds[8].get_text(strip=True) if len(tds) > 8 else ""
        teacher_td = tds[9] if len(tds) > 9 else None

        points_parts = points_raw.split("/") if points_raw else []
        points_earned = points_parts[0].strip() if len(points_parts) == 2 else None
        points_max = points_parts[1].strip() if len(points_parts) == 2 else None

        teacher_link = teacher_td.select_one("a") if teacher_td else None
        teacher = teacher_link.get_text(strip=True) if teacher_link else ""
        teacher_id = _href_id(teacher_link["href"] if teacher_link else None, "/inside/profile/")

        if task_id_val is None:
            continue

        tasks.append(Task(
            task_id=task_id_val,
            discipline=discipline,
            discipline_id=discipline_id,
            name=name,
            status=status,
            points_earned=points_earned,
            points_max=points_max,
            task_type=task_type,
            deadline=deadline if deadline and deadline != "Не указана" else None,
            updated_at=updated_at,
            teacher=teacher,
            teacher_id=teacher_id,
        ))

    return tasks


def get_task(cookie: str, task_id: int) -> TaskDetail:
    """Fetch full details for a single task."""
    with _make_client(cookie) as client:
        r = client.get(f"/inside/student/tasks/{task_id}")
        r.raise_for_status()

    soup = BeautifulSoup(r.text, "lxml")

    # Task name: h3.page__title
    name_el = soup.select_one("h3.page__title")
    task_name = name_el.get_text(strip=True) if name_el else ""

    # Metadata: all h5 tags. Structure: "Key: <span>value</span>"
    disc_link = soup.select_one("h5 a[href*='/inside/students/subjects/']")
    discipline = disc_link.get_text(strip=True) if disc_link else ""
    discipline_id = _href_id(disc_link["href"] if disc_link else None, "/inside/students/subjects/")

    teacher_link = soup.select_one("h5 a[href*='/inside/profile/']")
    teacher = teacher_link.get_text(strip=True) if teacher_link else ""
    teacher_id = _href_id(teacher_link["href"] if teacher_link else None, "/inside/profile/")

    info: dict[str, str] = {}
    for h in soup.select("h5"):
        text = h.get_text(" ", strip=True)
        for key in ("Тип:", "Семестр:", "Баллы:", "№ задания:", "Дата добавления:",
                    "Доступные расширения файлов отчета:", "Предельная дата выполнения:"):
            if text.startswith(key):
                val_el = h.select_one("span")
                info[key] = val_el.get_text(strip=True) if val_el else text[len(key):].strip()

    # Description: <p> sibling after h5 "Описание задания"
    desc = ""
    for h in soup.select("h5"):
        if "Описание задания" in h.get_text():
            sibling = h.find_next_sibling()
            while sibling:
                t = sibling.get_text(" ", strip=True)
                if t:
                    desc = t
                    break
                sibling = sibling.find_next_sibling()
            break

    # Extra materials: links inside h5 "Доп. материалы"
    extra_materials = []
    for h in soup.select("h5"):
        if "Доп. материалы" in h.get_text():
            for a in h.select("a"):
                href = a.get("href", "")
                if href:
                    extra_materials.append({"text": a.get_text(strip=True), "url": href})
            break

    # Reports table: after h4 "Мои отчеты"
    reports = []
    for h in soup.select("h4"):
        if "Мои отчеты" in h.get_text():
            table = h.find_next("table")
            if table:
                for row in table.select("tr"):
                    tds = row.select("td")
                    if not tds:
                        continue
                    status = tds[0].get_text(strip=True)
                    file_link = tds[1].select_one("a") if len(tds) > 1 else None
                    href = file_link["href"] if file_link else ""
                    file_url = (BASE_URL + href if href.startswith("/") else href) if href else None
                    uploaded_at = tds[2].get_text(strip=True) if len(tds) > 2 else ""
                    checked_at = tds[3].get_text(strip=True) if len(tds) > 3 else ""
                    student_comment = tds[4].get_text(strip=True) if len(tds) > 4 else ""
                    teacher_comment = tds[5].get_text(strip=True) if len(tds) > 5 else ""
                    if status:
                        reports.append({
                            "status": status,
                            "file_url": file_url,
                            "uploaded_at": uploaded_at,
                            "checked_at": checked_at,
                            "student_comment": student_comment,
                            "teacher_comment": teacher_comment,
                        })
            break

    # CSRF token from the add-report form (only present when no report submitted yet)
    csrf_input = soup.select_one("#add-report-form input[name='token']")
    csrf_token = csrf_input["value"] if csrf_input else ""

    return TaskDetail(
        task_id=task_id,
        name=task_name,
        discipline=discipline,
        discipline_id=discipline_id,
        task_type=info.get("Тип:", ""),
        semester=info.get("Семестр:", ""),
        teacher=teacher,
        teacher_id=teacher_id,
        points_max=info.get("Баллы:", None),
        order_num=info.get("№ задания:", None),
        added_at=info.get("Дата добавления:", None),
        allowed_extensions=info.get("Доступные расширения файлов отчета:", "Все"),
        deadline=info.get("Предельная дата выполнения:", None) or None,
        description=desc,
        extra_materials=extra_materials,
        reports=reports,
        csrf_token=csrf_token,
    )


def get_materials(
    cookie: str,
    semester: Optional[int] = None,
    subject: Optional[int] = None,
) -> list[Material]:
    """Fetch all learning materials with optional filters."""
    all_materials: list[Material] = []
    page = 1

    base_params: dict = {}
    if semester is not None:
        base_params["semester"] = semester
    if subject is not None:
        base_params["subject"] = subject

    with _make_client(cookie) as client:
        while True:
            r = client.get("/inside/student/materials", params={**base_params, "page": page})
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "lxml")
            table = soup.select_one("table")
            if not table:
                break

            rows = table.select("tr")
            found_any = False
            for row in rows:
                tds = row.select("td")
                if not tds:
                    continue
                # Layout: [file-icon-link, external-link?, discipline, name, date, teacher]
                links_in_first = tds[0].select("a")
                download_url = ""
                external_url = None
                for a in links_in_first:
                    href = a.get("href", "")
                    if "/inside/student/materials/" in href and "/download" in href:
                        download_url = BASE_URL + href if href.startswith("/") else href
                    elif href.startswith("http"):
                        external_url = href

                # second <a> in first td may be external
                if not external_url and len(tds) > 1:
                    ext_a = tds[1].select_one("a")
                    if ext_a and ext_a.get("href", "").startswith("http"):
                        external_url = ext_a["href"]

                # Layout: 0=Файл/Ссылки, 1=Дисциплина, 2=Название, 3=Дата, 4=Преподаватель
                disc_link = tds[1].select_one("a") if len(tds) > 1 else None
                discipline = disc_link.get_text(strip=True) if disc_link else ""
                discipline_id = _href_id(disc_link["href"] if disc_link else None, "/inside/students/subjects/")

                name = tds[2].get_text(strip=True) if len(tds) > 2 else ""
                added_at = tds[3].get_text(strip=True) if len(tds) > 3 else ""
                teacher_td = tds[4] if len(tds) > 4 else None
                teacher_link = teacher_td.select_one("a") if teacher_td else None
                teacher = teacher_link.get_text(strip=True) if teacher_link else (teacher_td.get_text(strip=True) if teacher_td else "")
                teacher_id = _href_id(teacher_link["href"] if teacher_link else None, "/inside/profile/")

                if not name:
                    continue

                all_materials.append(Material(
                    download_url=download_url,
                    external_url=external_url,
                    discipline=discipline,
                    discipline_id=discipline_id,
                    name=name,
                    added_at=added_at,
                    teacher=teacher,
                    teacher_id=teacher_id,
                ))
                found_any = True

            # Check for next page
            next_link = soup.select_one("nav a[href*='page=']")
            if not next_link or not found_any:
                break
            page += 1

    return all_materials


def get_profile(cookie: str) -> Profile:
    """Fetch the current student's own profile page."""
    with _make_client(cookie) as client:
        r = client.get("/inside/profile")
        r.raise_for_status()

    soup = BeautifulSoup(r.text, "lxml")

    name_el = soup.select_one("h3.text-center")
    full_name = name_el.get_text(strip=True) if name_el else ""

    info: dict[str, str] = {}
    for h in soup.select("h5"):
        text = re.sub(r"\s+", " ", h.get_text(" ", strip=True))
        for key in (
            "Группа:",
            "Номер студенческого билета/ зачетной книжки:",
            "Институт/факультет:",
            "Специальность:",
            "Направленность:",
            "Форма обучения:",
            "Уровень профессионального образования:",
            "Статус:",
        ):
            if text.startswith(key):
                val_el = h.select_one("span")
                val = val_el.get_text(strip=True) if val_el else re.sub(r"\s+", " ", text[len(key):]).strip()
                info[key] = val

    return Profile(
        full_name=full_name,
        group=info.get("Группа:", ""),
        student_id=info.get("Номер студенческого билета/ зачетной книжки:", ""),
        institute=info.get("Институт/факультет:"),
        specialty=info.get("Специальность:"),
        direction=info.get("Направленность:"),
        study_form=info.get("Форма обучения:"),
        education_level=info.get("Уровень профессионального образования:"),
        status=info.get("Статус:"),
    )


def get_teacher_profile(cookie: str, teacher_id: int) -> TeacherProfile:
    """Fetch a teacher's profile page."""
    with _make_client(cookie) as client:
        r = client.get(f"/inside/profile/{teacher_id}")
        r.raise_for_status()

    soup = BeautifulSoup(r.text, "lxml")

    name_el = soup.select_one("h3.text-center")
    full_name = name_el.get_text(strip=True) if name_el else ""

    degree_el = soup.select_one("h4.text-center")
    if degree_el:
        raw = re.sub(r"\s+", " ", degree_el.get_text(" ", strip=True))
        degree: Optional[str] = re.sub(r"\s*,\s*", ", ", raw).strip(", ") or None
    else:
        degree = None

    positions: list[dict] = []
    items = soup.select(".list-group-item")
    pos_idx = next(
        (i for i, item in enumerate(items) if item.get_text(strip=True) == "Позиции"),
        None,
    )
    if pos_idx is not None:
        for item in items[pos_idx + 1:]:
            if "fw-semibold" in (item.get("class") or []):
                break
            h5_el = item.select_one("h5")
            if not h5_el:
                continue
            divs = [
                d.get_text(strip=True)
                for d in item.find_all("div", recursive=False)
                if d.get_text(strip=True)
            ]
            positions.append({
                "position": h5_el.get_text(strip=True),
                "department": divs[0] if divs else None,
                "organization": divs[1] if len(divs) > 1 else None,
            })

    return TeacherProfile(
        teacher_id=teacher_id,
        full_name=full_name,
        degree=degree,
        positions=positions,
    )


def get_subject(cookie: str, subject_id: int) -> SubjectDetail:
    """Fetch a subject/discipline detail page."""
    with _make_client(cookie) as client:
        r = client.get(f"/inside/students/subjects/{subject_id}")
        r.raise_for_status()

    soup = BeautifulSoup(r.text, "lxml")

    name_el = soup.select_one("h3.page__title")
    name = name_el.get_text(strip=True) if name_el else ""

    info: dict[str, str] = {}
    for h in soup.select("h5"):
        text = re.sub(r"\s+", " ", h.get_text(" ", strip=True))
        for key in (
            "Кафедра:",
            "Год / семестр:",
            "Тип контроля:",
            "Оценка за аттестацию:",
            "Количество часов:",
        ):
            if text.startswith(key):
                val_el = h.select_one("span.fw-light")
                val = (
                    re.sub(r"\s+", " ", val_el.get_text(" ", strip=True)).strip()
                    if val_el
                    else re.sub(r"\s+", " ", text[len(key):]).strip()
                )
                info[key] = val

    teacher_name: Optional[str] = None
    teacher_id_val: Optional[int] = None
    teacher_position: Optional[str] = None
    lesson_types: Optional[str] = None
    groups: Optional[str] = None

    for card in soup.select(".card"):
        header = card.select_one(".card-header")
        if not (header and "Преподаватель" in header.get_text()):
            continue
        body = card.select_one(".card-body")
        if not body:
            continue
        teacher_h5 = body.select_one("h5")
        if teacher_h5:
            teacher_name = teacher_h5.get_text(strip=True)
        teacher_link = body.select_one("a[href*='/inside/profile/']")
        if teacher_link:
            teacher_id_val = _href_id(teacher_link.get("href"), "/inside/profile/")
        lines = [l.strip() for l in body.get_text("\n").split("\n") if l.strip()]
        for i, line in enumerate(lines):
            if line == teacher_name and i + 1 < len(lines):
                nxt = lines[i + 1]
                if not nxt.startswith("Типы") and not nxt.startswith("Группы"):
                    teacher_position = nxt
            if line.startswith("Типы занятий:"):
                lesson_types = line[len("Типы занятий:"):].strip()
            if line.startswith("Группы:"):
                groups = line[len("Группы:"):].strip()
        break

    return SubjectDetail(
        subject_id=subject_id,
        name=name,
        department=info.get("Кафедра:"),
        year_semester=info.get("Год / семестр:"),
        control_type=info.get("Тип контроля:"),
        grade=info.get("Оценка за аттестацию:"),
        hours=info.get("Количество часов:"),
        teacher=teacher_name,
        teacher_id=teacher_id_val,
        teacher_position=teacher_position,
        lesson_types=lesson_types,
        groups=groups,
    )


def get_group_order(cookie: str) -> dict:
    """Return the current student's order number in their group list."""
    profile = get_profile(cookie)

    with _make_client(cookie) as client:
        r = client.get("/inside/student/groups")
        r.raise_for_status()

    soup = BeautifulSoup(r.text, "lxml")
    table = soup.select_one("table")
    if not table:
        return {"order_num": None, "total": 0, "full_name": profile.full_name, "group": profile.group}

    order_num: Optional[str] = None
    total = 0
    for row in table.select("tr"):
        tds = row.select("td")
        if len(tds) < 4:
            continue
        total += 1
        if tds[3].get_text(strip=True) == profile.student_id or tds[1].get_text(strip=True) == profile.full_name:
            order_num = tds[0].get_text(strip=True)

    return {
        "order_num": int(order_num) if order_num and order_num.isdigit() else order_num,
        "total": total,
        "full_name": profile.full_name,
        "group": profile.group,
    }


def submit_report(cookie: str, task_id: int, file_path: str, comment: str = "") -> dict:
    """Submit a report file for a task. Returns result info."""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    with _make_client(cookie) as client:
        # Step 1: GET task page to extract CSRF token
        r = client.get(f"/inside/student/tasks/{task_id}")
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "lxml")

        csrf_input = soup.select_one("#add-report-form input[name='token']")
        if not csrf_input:
            # Try any form with action matching store
            for form in soup.select("form"):
                if f"reports/{task_id}/store" in form.get("action", ""):
                    csrf_input = form.select_one("input[name='token']")
                    break

        if not csrf_input:
            raise RuntimeError("Could not find CSRF token on task page. Is the task accessible?")

        csrf_token = csrf_input["value"]

        # Step 2: POST multipart form with file
        with open(path, "rb") as f:
            r2 = client.post(
                f"/inside/student/reports/{task_id}/store",
                data={"token": csrf_token, "comment": comment},
                files={"file": (path.name, f, _guess_mime(path))},
            )
        r2.raise_for_status()

    # Parse response to check success
    soup2 = BeautifulSoup(r2.text, "lxml")
    # Look for error messages or success indicators
    error_els = soup2.select(".alert-danger, .error, .alert-error")
    success_els = soup2.select(".alert-success, .success")

    errors = [e.get_text(strip=True) for e in error_els if e.get_text(strip=True)]
    successes = [e.get_text(strip=True) for e in success_els if e.get_text(strip=True)]

    # If redirected back to task page and reports table has new entry — success
    new_reports_table = soup2.select_one("table")
    report_rows = new_reports_table.select("tr td") if new_reports_table else []

    return {
        "success": not errors,
        "errors": errors,
        "messages": successes,
        "final_url": str(r2.url),
    }


DOWNLOAD_DIR = Path.home() / "Downloads" / "guap-materials"


def download_material(cookie: str, url: str, save_dir: Optional[str] = None) -> dict:
    """Download a material file from pro.guap.ru or an external URL.

    Returns a dict with keys: path, filename, size, content_type, source.
    """
    out_dir = Path(save_dir) if save_dir else DOWNLOAD_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    # Normalise URL
    if url.startswith("/"):
        url = BASE_URL + url

    source = _classify_url(url)

    if source == "guap":
        result = _download_guap(cookie, url, out_dir)
    elif source == "gdrive":
        result = _download_gdrive(url, out_dir)
    else:
        result = _download_direct(url, out_dir)

    return result


def _classify_url(url: str) -> str:
    if "pro.guap.ru" in url or url.startswith("/"):
        return "guap"
    if "drive.google.com" in url or "docs.google.com" in url:
        return "gdrive"
    return "direct"


def _safe_filename(name: str) -> str:
    """Sanitise a filename, keeping Cyrillic and Latin characters."""
    name = re.sub(r'[\\/*?:"<>|]', "_", name).strip(". ")
    return name[:200] or "file"


def _filename_from_response(r: httpx.Response, fallback: str = "file") -> str:
    cd = r.headers.get("content-disposition", "")
    # Try filename*=UTF-8''... first (RFC 5987)
    m = re.search(r"filename\*\s*=\s*UTF-8''([^\s;]+)", cd, re.IGNORECASE)
    if m:
        from urllib.parse import unquote
        return _safe_filename(unquote(m.group(1)))
    # Then regular filename=
    m = re.search(r'filename\s*=\s*["\']?([^"\';\r\n]+)', cd, re.IGNORECASE)
    if m:
        name = m.group(1).strip().strip('"\'')
        try:
            name = name.encode("latin-1").decode("utf-8")
        except Exception:
            pass
        return _safe_filename(name)
    # Guess from URL path
    from urllib.parse import urlparse, unquote
    path_part = urlparse(r.url.path if hasattr(r.url, "path") else str(r.url)).path
    name = unquote(path_part.rstrip("/").split("/")[-1])
    if "." in name:
        return _safe_filename(name)
    # Fallback: use supplied name + extension from content-type
    ct = r.headers.get("content-type", "")
    ext_map = {
        "application/pdf": ".pdf",
        "application/msword": ".doc",
        "application/vnd.openxmlformats": ".docx",
        "application/zip": ".zip",
        "text/plain": ".txt",
    }
    ext = ""
    for mime, e in ext_map.items():
        if ct.startswith(mime):
            ext = e
            break
    return _safe_filename(fallback) + ext


def _write_file(out_dir: Path, filename: str, content: bytes) -> Path:
    target = out_dir / filename
    # Avoid overwriting existing files
    if target.exists():
        stem, suffix = target.stem, target.suffix
        i = 1
        while target.exists():
            target = out_dir / f"{stem}_{i}{suffix}"
            i += 1
    target.write_bytes(content)
    return target


def _download_guap(cookie: str, url: str, out_dir: Path) -> dict:
    with _make_client(cookie) as client:
        r = client.get(url)
        r.raise_for_status()
    filename = _filename_from_response(r, fallback="guap_material")
    path = _write_file(out_dir, filename, r.content)
    return {
        "path": str(path),
        "filename": path.name,
        "size": len(r.content),
        "content_type": r.headers.get("content-type", ""),
        "source": "pro.guap.ru",
    }


def _download_gdrive(url: str, out_dir: Path) -> dict:
    """Download a Google Drive file, handling the virus-scan confirmation page."""
    file_id = _gdrive_file_id(url)
    if not file_id:
        raise ValueError(f"Could not extract Google Drive file ID from: {url}")

    download_url = f"https://drive.usercontent.google.com/download?id={file_id}&export=download&confirm=t"

    with httpx.Client(
        follow_redirects=True,
        timeout=60,
        headers={"User-Agent": "Mozilla/5.0"},
    ) as client:
        r = client.get(download_url)
        r.raise_for_status()

        content_type = r.headers.get("content-type", "")

        # If we still got HTML, try the older /uc endpoint with confirmation
        if "text/html" in content_type:
            soup = BeautifulSoup(r.text, "lxml")
            # Look for the download form or confirm link
            confirm_url = None
            for a in soup.select("a"):
                href = a.get("href", "")
                if "confirm" in href and ("uc?" in href or "usercontent" in href):
                    confirm_url = href if href.startswith("http") else "https://drive.google.com" + href
                    break
            if not confirm_url:
                # Try /uc fallback
                confirm_url = f"https://drive.google.com/uc?export=download&id={file_id}&confirm=t"
            r = client.get(confirm_url)
            r.raise_for_status()
            content_type = r.headers.get("content-type", "")

        if "text/html" in content_type:
            raise RuntimeError(
                f"Google Drive returned HTML instead of a file for ID {file_id}. "
                "The file may be restricted or require sign-in."
            )

    filename = _filename_from_response(r, fallback=f"gdrive_{file_id}")
    path = _write_file(out_dir, filename, r.content)
    return {
        "path": str(path),
        "filename": path.name,
        "size": len(r.content),
        "content_type": content_type,
        "source": "Google Drive",
    }


def _gdrive_file_id(url: str) -> Optional[str]:
    m = re.search(r"/file/d/([a-zA-Z0-9_-]+)", url)
    if m:
        return m.group(1)
    m = re.search(r"[?&]id=([a-zA-Z0-9_-]+)", url)
    return m.group(1) if m else None


def _download_direct(url: str, out_dir: Path) -> dict:
    """Download any direct URL (PDF, etc.)."""
    with httpx.Client(
        follow_redirects=True,
        timeout=60,
        headers={"User-Agent": "Mozilla/5.0"},
    ) as client:
        r = client.get(url)
        r.raise_for_status()

    content_type = r.headers.get("content-type", "")
    if "text/html" in content_type:
        raise RuntimeError(
            f"URL returned HTML instead of a file. "
            "This may be a web page, not a direct download link."
        )

    from urllib.parse import urlparse, unquote
    filename = _filename_from_response(r, fallback=unquote(urlparse(url).path.split("/")[-1]) or "file")
    path = _write_file(out_dir, filename, r.content)
    return {
        "path": str(path),
        "filename": path.name,
        "size": len(r.content),
        "content_type": content_type,
        "source": url,
    }


def _guess_mime(path: Path) -> str:
    ext = path.suffix.lower()
    types = {
        ".pdf": "application/pdf",
        ".doc": "application/msword",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".zip": "application/zip",
        ".rar": "application/x-rar-compressed",
        ".py": "text/x-python",
        ".txt": "text/plain",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
    }
    return types.get(ext, "application/octet-stream")
