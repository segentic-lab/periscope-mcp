import json
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional
import config


@dataclass
class FormLogin:
    login_url: str
    username: str
    password: str
    username_selector: str = "input[name='username'], input[name='email'], input[type='email'], #username, #email"
    password_selector: str = "input[name='password'], input[type='password'], #password"
    submit_selector: str = "button[type='submit'], input[type='submit'], button:has-text('Login'), button:has-text('Sign in')"
    success_indicator: str = ""


@dataclass
class BasicAuth:
    username: str
    password: str


@dataclass
class CookieAuth:
    # List of cookie dicts: {name, value, domain, path, secure?, httpOnly?}.
    # Playwright's add_cookies requires either url or a domain+path pair.
    cookies: list


@dataclass
class ProjectAuth:
    method: str = ""  # "form", "basic", "cookies"
    form_login: Optional[FormLogin] = None
    basic_auth: Optional[BasicAuth] = None
    cookie_auth: Optional[CookieAuth] = None


@dataclass
class Project:
    name: str
    base_url: str
    auth: Optional[ProjectAuth] = None
    max_pages: int = 20
    max_depth: int = 3
    test_types: list = field(default_factory=lambda: ["visual", "accessibility", "seo", "performance", "functionality", "geo"])
    created_at: str = ""
    last_tested: str = ""
    is_logged_in: bool = False
    screenshot_dir: Optional[str] = None

    def to_dict(self) -> dict:
        data = {
            "name": self.name,
            "base_url": self.base_url,
            "max_pages": self.max_pages,
            "max_depth": self.max_depth,
            "test_types": self.test_types,
            "created_at": self.created_at,
            "last_tested": self.last_tested,
            "is_logged_in": self.is_logged_in,
            "screenshot_dir": self.screenshot_dir,
            "auth": None
        }
        if self.auth:
            auth_data = {"method": self.auth.method}
            if self.auth.form_login:
                auth_data["form_login"] = asdict(self.auth.form_login)
            if self.auth.basic_auth:
                auth_data["basic_auth"] = asdict(self.auth.basic_auth)
            if self.auth.cookie_auth:
                auth_data["cookie_auth"] = {"cookies": self.auth.cookie_auth.cookies}
            data["auth"] = auth_data
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "Project":
        auth = None
        if data.get("auth"):
            auth_data = data["auth"]
            auth = ProjectAuth(method=auth_data.get("method", ""))
            if auth_data.get("form_login"):
                auth.form_login = FormLogin(**auth_data["form_login"])
            if auth_data.get("basic_auth"):
                auth.basic_auth = BasicAuth(**auth_data["basic_auth"])
            if auth_data.get("cookie_auth"):
                auth.cookie_auth = CookieAuth(cookies=auth_data["cookie_auth"]["cookies"])

        return cls(
            name=data["name"],
            base_url=data["base_url"],
            auth=auth,
            max_pages=data.get("max_pages", 20),
            max_depth=data.get("max_depth", 3),
            test_types=data.get("test_types", ["visual", "accessibility", "seo", "performance", "functionality", "geo"]),
            created_at=data.get("created_at", ""),
            last_tested=data.get("last_tested", ""),
            is_logged_in=data.get("is_logged_in", False),
            screenshot_dir=data.get("screenshot_dir", None)
        )


class ProjectManager:
    def __init__(self):
        self.projects: dict[str, Project] = {}
        self._load()

    def _load(self):
        if not os.path.exists(config.PROJECTS_FILE):
            return
        try:
            with open(config.PROJECTS_FILE, "r") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            # A corrupt store must not prevent server startup; keep the bad
            # file aside for manual recovery instead of overwriting it.
            backup = config.PROJECTS_FILE + ".corrupt"
            try:
                os.replace(config.PROJECTS_FILE, backup)
            except OSError:
                backup = None
            print(f"WARNING: could not load {config.PROJECTS_FILE} ({e});"
                  f" starting empty{f', original moved to {backup}' if backup else ''}")
            return
        for name, proj_data in data.items():
            self.projects[name] = Project.from_dict(proj_data)
        # Login state lives in in-memory browser contexts, which don't survive
        # a server restart — a persisted True flag would always be stale.
        self.reset_login_flags(save=False)

    def _save(self):
        os.makedirs(os.path.dirname(config.PROJECTS_FILE), exist_ok=True)
        data = {name: proj.to_dict() for name, proj in self.projects.items()}
        # Atomic write: a crash mid-write must not corrupt the store, and the
        # file holds plaintext credentials, so keep it owner-only.
        tmp = config.PROJECTS_FILE + ".tmp"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, config.PROJECTS_FILE)

    def reset_login_flags(self, save: bool = True):
        """Clear is_logged_in on all projects (login state died with the browser)."""
        changed = False
        for p in self.projects.values():
            if p.is_logged_in:
                p.is_logged_in = False
                changed = True
        if changed and save:
            self._save()

    def create(self, name: str, base_url: str, **kwargs) -> Project:
        if name in self.projects:
            raise ValueError(f"Project '{name}' already exists")

        # Ensure URL has scheme
        if not base_url.startswith(("http://", "https://")):
            base_url = "https://" + base_url

        project = Project(
            name=name,
            base_url=base_url.rstrip("/"),
            created_at=datetime.now().isoformat(),
            **kwargs
        )
        self.projects[name] = project
        self._save()
        return project

    def get(self, name: str) -> Optional[Project]:
        return self.projects.get(name)

    def list_all(self) -> list[dict]:
        return [
            {
                "name": p.name,
                "base_url": p.base_url,
                "last_tested": p.last_tested,
                "has_auth": p.auth is not None and p.auth.method != "",
                "is_logged_in": p.is_logged_in
            }
            for p in self.projects.values()
        ]

    def delete(self, name: str) -> bool:
        project = self.projects.get(name)
        if not project:
            return False
        custom_dir = project.screenshot_dir
        del self.projects[name]
        self._save()
        # Clean up project screenshots (default dir + custom screenshot_dir if set)
        import shutil
        for base in (config.SCREENSHOT_DIR, custom_dir):
            if not base:
                continue
            project_screenshot_dir = os.path.join(base, name)
            if os.path.exists(project_screenshot_dir):
                shutil.rmtree(project_screenshot_dir)
        return True

    def set_form_login(
        self,
        name: str,
        login_url: str,
        username: str,
        password: str,
        username_selector: str = None,
        password_selector: str = None,
        submit_selector: str = None
    ) -> bool:
        project = self.get(name)
        if not project:
            return False

        form_login = FormLogin(
            login_url=login_url,
            username=username,
            password=password
        )
        if username_selector:
            form_login.username_selector = username_selector
        if password_selector:
            form_login.password_selector = password_selector
        if submit_selector:
            form_login.submit_selector = submit_selector

        project.auth = ProjectAuth(method="form", form_login=form_login)
        project.is_logged_in = False
        self._save()
        return True

    def set_basic_auth(self, name: str, username: str, password: str) -> bool:
        project = self.get(name)
        if not project:
            return False

        project.auth = ProjectAuth(
            method="basic",
            basic_auth=BasicAuth(username=username, password=password)
        )
        self._save()
        return True

    def set_cookies(self, name: str, cookies: list) -> bool:
        project = self.get(name)
        if not project:
            return False

        project.auth = ProjectAuth(
            method="cookies",
            cookie_auth=CookieAuth(cookies=cookies)
        )
        self._save()
        return True

    def mark_logged_in(self, name: str, logged_in: bool = True):
        project = self.get(name)
        if project:
            project.is_logged_in = logged_in
            self._save()

    def update_last_tested(self, name: str):
        project = self.get(name)
        if project:
            project.last_tested = datetime.now().isoformat()
            self._save()
