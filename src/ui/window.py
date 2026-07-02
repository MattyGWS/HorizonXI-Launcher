import html
import json
import threading
import urllib.request
import urllib.parse
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gio, GLib, Gtk, Gdk

from config import DATA_DIR, GAME_DIR
from addons.addon_manager import AddonManager
from addons.plugin_manager import PluginManager
from settings.settings_manager import GameSettings, SettingsManager
from install.install import InstallManager
from launcher.horizon_manager import HorizonManager
from launcher.launcher import Launcher
from proton.proton_manager import ProtonManager


HORIZON_STATUS_URL = "https://api.horizonxi.com/api/v1/misc/status"
HORIZON_YELLS_URL = "https://api.horizonxi.com/api/v1/misc/yells"
HORIZON_NEWS_URL = "https://horizonxi.com/news.json"
HORIZON_CHARS_URL = "https://api.horizonxi.com/api/v1/chars"
HORIZON_CHAR_URL = "https://api.horizonxi.com/api/v1/chars/{name}"
HORIZON_BAZAAR_URL = "https://api.horizonxi.com/api/v1/items/bazaar"

YELLS_REFRESH_SECONDS = 15
NEWS_REFRESH_SECONDS = 1800
FRIENDS_REFRESH_SECONDS = 60

VANA_EPOCH = datetime(2001, 12, 31, 15, 0, 0, tzinfo=timezone.utc)
VANA_START_YEAR = 886
VANA_TIME_MULTIPLIER = 25
VANA_SECONDS_PER_DAY = 24 * 60 * 60
VANA_DAYS_PER_MONTH = 30
VANA_MONTHS_PER_YEAR = 12
VANA_DAYS_PER_YEAR = VANA_DAYS_PER_MONTH * VANA_MONTHS_PER_YEAR
VANA_MOON_CYCLE_DAYS = 84

VANA_WEEKDAYS = (
    ("Firesday", "#ef4444"),
    ("Earthsday", "#c58f2f"),
    ("Watersday", "#3b82f6"),
    ("Windsday", "#22c55e"),
    ("Iceday", "#67e8f9"),
    ("Lightningday", "#d946ef"),
    ("Lightsday", "#facc15"),
    ("Darksday", "#a78bfa"),
)

CREDENTIALS_FILE = DATA_DIR / "credentials.json"
FRIENDS_FILE = DATA_DIR / "friends.json"

MAIN_ACTION_INSTALL = "install"
MAIN_ACTION_MAINTENANCE = "maintenance"
MAIN_ACTION_LOGIN = "login"
MAIN_ACTION_LAUNCH = "launch"
MAIN_ACTION_UPDATE = "update"
MAIN_ACTION_CHECKING_UPDATE = "checking_update"
MAIN_ACTION_UPDATE_CHECK_FAILED = "update_check_failed"
MAIN_ACTION_BUSY = "busy"


class HorizonWindow(Adw.Application):
    def __init__(self):
        super().__init__(application_id="io.github.mattyws.HorizonXILauncher")
        self.connect("activate", self.on_activate)

        self.proton = ProtonManager()
        self.horizon = HorizonManager()

        self.installer = InstallManager(self.proton, self.horizon)
        self.launcher = Launcher(self.proton, self.horizon)
        self.addon_manager = AddonManager()
        self.plugin_manager = PluginManager()
        self.settings_manager = SettingsManager()

        self.window = None

        self.proton_status = None
        self.game_status = None
        self.server_status = None
        self.players_status = None
        self.vana_time_label = None
        self.vana_day_label = None

        self.settings_controls = {}
        self.settings_stack = None

        self.status_label = None
        self.progress_bar = None

        self.install_button = None
        self.launch_button = None
        self.launch_game_button = None
        self.reset_button = None
        self.gamepad_button = None
        self.backup_macros_button = None
        self.open_folder_button = None

        self.username_entry = None
        self.password_entry = None
        self.remember_check = None
        self.addons_rows_box = None
        self.addons_refresh_button = None
        self.plugins_rows_box = None
        self.polplugins_rows_box = None
        self.extensions_refresh_button = None

        self.yells_rows_box = None
        self.yells_status_label = None
        self.news_rows_box = None
        self.news_status_label = None
        self.friends_rows_box = None
        self.friends_status_label = None
        self.friend_names = []
        self.characters_cache = []
        self.characters_by_name = {}

        self.server_online = False
        self.players_online = None
        self.operation_in_progress = False
        self.main_action_state = MAIN_ACTION_INSTALL
        self.loading_saved_credentials = False
        self.game_update_available = False
        self.game_update_check_in_progress = False
        self.game_update_check_failed = False
        self.game_update_details = None

    def on_activate(self, app):
        self.window = Adw.ApplicationWindow(application=app)
        self.window.set_title("HorizonXI Launcher")
        self.window.set_default_size(1120, 640)
        self.window.set_size_request(900, 560)

        toolbar_view = Adw.ToolbarView()
        header = Adw.HeaderBar()
        toolbar_view.add_top_bar(header)

        root_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=10,
            margin_top=14,
            margin_bottom=14,
            margin_start=24,
            margin_end=24,
        )

        header_overlay = Gtk.Overlay()
        header_overlay.set_vexpand(False)

        header_center_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=10,
        )
        header_center_box.set_halign(Gtk.Align.FILL)

        title = Gtk.Label(label="HorizonXI Launcher")
        title.add_css_class("title-1")
        title.set_halign(Gtk.Align.CENTER)
        header_center_box.append(title)

        stack = Gtk.Stack()
        stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        stack.set_vhomogeneous(False)
        stack.set_hhomogeneous(False)
        stack.set_vexpand(False)

        switcher = Gtk.StackSwitcher()
        switcher.set_stack(stack)
        switcher.set_halign(Gtk.Align.CENTER)
        header_center_box.append(switcher)

        header_overlay.set_child(header_center_box)

        vanadiel_card = self.build_vanadiel_time_card()
        vanadiel_card.set_halign(Gtk.Align.START)
        vanadiel_card.set_valign(Gtk.Align.END)
        header_overlay.add_overlay(vanadiel_card)

        root_box.append(header_overlay)

        stack.add_titled(self.build_main_page(), "main", "Main")
        stack.add_titled(self.build_addons_page(), "addons", "Addons")
        stack.add_titled(self.build_community_page(), "community", "Community")
        stack.add_titled(self.build_settings_page(), "settings", "Settings")

        root_box.append(stack)

        version_label = Gtk.Label(label="Version 0.3.0")
        version_label.add_css_class("dim-label")
        version_label.set_margin_top(2)
        root_box.append(version_label)

        toolbar_view.set_content(root_box)
        self.window.set_content(toolbar_view)
        self.load_custom_css()

        self.load_saved_credentials()
        self.load_friends()
        self.refresh_status()
        self.refresh_game_update_status_async()
        self.refresh_server_status_async()
        self.refresh_yells_async()
        self.refresh_news_async()
        self.refresh_friends_async()

        GLib.timeout_add_seconds(60, self.refresh_server_status_async)
        GLib.timeout_add_seconds(YELLS_REFRESH_SECONDS, self.refresh_yells_async)
        GLib.timeout_add_seconds(NEWS_REFRESH_SECONDS, self.refresh_news_async)
        GLib.timeout_add_seconds(FRIENDS_REFRESH_SECONDS, self.refresh_friends_async)
        GLib.idle_add(self.update_vanadiel_time)
        GLib.timeout_add_seconds(1, self.update_vanadiel_time)

        self.window.present()

    def load_custom_css(self):
        css = b"""
        .vanatime-panel {
            background: rgba(54, 54, 58, 0.58);
            border-radius: 10px;
            padding: 10px 14px;
        }

        .vanatime-divider {
            background: rgba(180, 180, 190, 0.35);
            min-height: 1px;
            margin-top: 4px;
            margin-bottom: 6px;
        }

        .yells-panel {
            background: rgba(28, 39, 62, 0.62);
            border-radius: 10px;
            padding: 6px;
        }

        .yell-row {
            padding: 6px 8px;
        }

        .yell-separator {
            background: rgba(118, 132, 160, 0.18);
            margin-left: 6px;
            margin-right: 6px;
            min-height: 1px;
        }

        .friends-panel {
            background: rgba(54, 54, 58, 0.72);
            border-radius: 10px;
            padding: 6px;
        }

        .friend-row {
            padding: 8px 8px;
        }

        .friend-separator {
            background: rgba(150, 150, 160, 0.16);
            margin-left: 6px;
            margin-right: 6px;
            min-height: 1px;
        }

        .friend-remove-button {
            padding-left: 10px;
            padding-right: 10px;
            min-height: 28px;
        }

        .update-action {
            background: @warning_color;
            color: @warning_fg_color;
        }
        """

        try:
            provider = Gtk.CssProvider()
            provider.load_from_data(css)
            display = Gdk.Display.get_default()
            if display:
                Gtk.StyleContext.add_provider_for_display(
                    display,
                    provider,
                    Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
                )
        except Exception as error:
            print(f"Failed to load custom CSS: {error}")

    def build_main_page(self):
        main_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=10,
        )
        main_box.set_vexpand(False)

        content_box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=24,
            homogeneous=True,
        )
        content_box.set_vexpand(False)

        left_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        content_box.append(left_box)

        right_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        content_box.append(right_box)

        status_group = Adw.PreferencesGroup(title="Status")

        self.proton_status = Adw.ActionRow(title="Proton GE 7-42")
        status_group.add(self.proton_status)

        self.game_status = Adw.ActionRow(title="HorizonXI Game")
        status_group.add(self.game_status)

        self.server_status = Adw.ActionRow(title="Server Status")
        self.server_status.set_subtitle("Checking...")
        status_group.add(self.server_status)

        self.players_status = Adw.ActionRow(title="Players Online")
        self.players_status.set_subtitle("Checking...")
        status_group.add(self.players_status)

        left_box.append(status_group)


        self.login_group = Adw.PreferencesGroup(title="Create an account on the HorizonXI Website")

        self.username_entry = Adw.EntryRow(title="Username")
        self.username_entry.connect("changed", self.on_credentials_changed)
        self.login_group.add(self.username_entry)

        self.password_entry = Adw.PasswordEntryRow(title="Password")
        self.password_entry.connect("changed", self.on_credentials_changed)
        self.login_group.add(self.password_entry)

        self.remember_check = Gtk.CheckButton(label="Remember credentials")
        self.remember_check.set_margin_top(8)
        self.remember_check.set_margin_bottom(8)
        self.remember_check.connect("toggled", self.on_remember_toggled)
        self.login_group.add(self.remember_check)

        self.launch_game_button = Gtk.Button(label="Install Game")
        self.launch_game_button.add_css_class("suggested-action")
        self.launch_game_button.connect("clicked", self.on_main_action_clicked)
        self.login_group.add(self.launch_game_button)

        self.progress_bar = Gtk.ProgressBar()
        self.progress_bar.set_show_text(True)
        self.progress_bar.set_text("Idle")
        self.progress_bar.set_fraction(0.0)
        self.login_group.add(self.progress_bar)

        self.status_label = Gtk.Label(label="Ready")
        self.status_label.set_wrap(True)
        self.status_label.set_xalign(0)
        self.status_label.add_css_class("dim-label")
        self.login_group.add(self.status_label)

        right_box.append(self.login_group)

        main_box.append(content_box)

        links_group = Adw.PreferencesGroup(title="HorizonXI Links")
        links_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        links_box.set_homogeneous(True)

        website_button = Gtk.Button(label="HorizonXI Website")
        website_button.connect("clicked", self.on_open_link_clicked, "https://horizonxi.com/")
        links_box.append(website_button)

        wiki_button = Gtk.Button(label="HorizonXI Wiki")
        wiki_button.connect("clicked", self.on_open_link_clicked, "https://horizonffxi.wiki/HorizonXI_Wiki")
        links_box.append(wiki_button)

        discord_button = Gtk.Button(label="HorizonXI Discord")
        discord_button.connect("clicked", self.on_open_link_clicked, "https://discord.gg/horizonxi")
        links_box.append(discord_button)

        links_group.add(links_box)
        main_box.append(links_group)

        return main_box

    def build_vanadiel_time_card(self):
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        card.add_css_class("vanatime-panel")
        card.set_halign(Gtk.Align.START)
        card.set_size_request(210, -1)

        title = Gtk.Label(label="Vana'diel Time")
        title.add_css_class("heading")
        title.set_xalign(0)
        card.append(title)

        divider = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        divider.add_css_class("vanatime-divider")
        card.append(divider)

        self.vana_time_label = Gtk.Label(label="--:-- ~ ----—--—--")
        self.vana_time_label.set_xalign(0)
        card.append(self.vana_time_label)

        self.vana_day_label = Gtk.Label()
        self.vana_day_label.set_xalign(0)
        self.vana_day_label.set_markup('<span foreground="#d946ef"><b>Loading...</b></span>')
        card.append(self.vana_day_label)

        return card

    def get_vanadiel_datetime(self, now=None):
        if now is None:
            now = datetime.now(timezone.utc)
        elif now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        else:
            now = now.astimezone(timezone.utc)

        elapsed_earth_seconds = max(0, int((now - VANA_EPOCH).total_seconds()))
        vana_elapsed_seconds = elapsed_earth_seconds * VANA_TIME_MULTIPLIER
        start_offset_seconds = VANA_START_YEAR * VANA_DAYS_PER_YEAR * VANA_SECONDS_PER_DAY
        total_vana_seconds = start_offset_seconds + vana_elapsed_seconds

        total_vana_days = total_vana_seconds // VANA_SECONDS_PER_DAY
        seconds_today = total_vana_seconds % VANA_SECONDS_PER_DAY

        year = total_vana_days // VANA_DAYS_PER_YEAR
        day_of_year = total_vana_days % VANA_DAYS_PER_YEAR
        month = (day_of_year // VANA_DAYS_PER_MONTH) + 1
        day = (day_of_year % VANA_DAYS_PER_MONTH) + 1
        hour = seconds_today // 3600
        minute = (seconds_today % 3600) // 60

        weekday_index = total_vana_days % len(VANA_WEEKDAYS)

        # Pyogenes/VanaTime/MithraPride moon formula.
        # The +26 offset is the important bit that keeps Horizon wiki/Pyogenes
        # aligned: without it, the moon percentage is consistently a few
        # Vana'diel days out even when the clock/date are correct.
        moon_raw_percent = self.get_vanadiel_moon_raw_percent(total_vana_days)
        moon_percent = int(round(abs(moon_raw_percent)))
        moon_icon = self.get_vanadiel_moon_icon(moon_raw_percent)

        return {
            "year": int(year),
            "month": int(month),
            "day": int(day),
            "hour": int(hour),
            "minute": int(minute),
            "weekday_index": int(weekday_index),
            "moon_percent": max(0, min(100, moon_percent)),
            "moon_icon": moon_icon,
        }

    def get_vanadiel_moon_raw_percent(self, total_vana_days):
        moon_value = (((int(total_vana_days) + 26) % VANA_MOON_CYCLE_DAYS) - (VANA_MOON_CYCLE_DAYS / 2))
        return (moon_value / (VANA_MOON_CYCLE_DAYS / 2)) * 100

    def get_vanadiel_moon_icon(self, moon_raw_percent):
        percent = abs(float(moon_raw_percent))
        waxing = moon_raw_percent >= 0

        if percent < 7:
            return "🌑"
        if percent >= 90:
            return "🌕"
        if percent < 40:
            return "☽" if waxing else "☾"
        if percent < 57:
            return "🌓" if waxing else "🌗"
        return "🌔" if waxing else "🌖"

    def update_vanadiel_time(self):
        if not self.vana_time_label or not self.vana_day_label:
            return True

        vana = self.get_vanadiel_datetime()
        day_name, day_color = VANA_WEEKDAYS[vana["weekday_index"]]

        self.vana_time_label.set_text(
            f'{vana["hour"]:02d}:{vana["minute"]:02d} ~ '
            f'{vana["year"]}-{vana["month"]}-{vana["day"]}'
        )
        self.vana_day_label.set_markup(
            f'<span foreground="{day_color}"><b>{html.escape(day_name)}</b></span>'
            f'  {html.escape(vana["moon_icon"])} {vana["moon_percent"]}%'
        )

        return True


    def build_community_page(self):
        page = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=18,
            homogeneous=True,
        )
        page.set_vexpand(True)

        yells_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        news_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        friends_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        page.append(yells_box)
        page.append(news_box)
        page.append(friends_box)

        yells_title = self._make_centered_section_title("Live Yells / Shouts")
        yells_box.append(yells_title)

        yells_group = Adw.PreferencesGroup(
            description="Recent in-game yells from HorizonXI. Refreshes frequently.",
        )

        self.yells_status_label = Gtk.Label(label="Loading yells...")
        self.yells_status_label.add_css_class("dim-label")
        self.yells_status_label.set_xalign(0)
        self.yells_status_label.set_margin_bottom(6)
        yells_group.add(self.yells_status_label)

        yells_scrolled = Gtk.ScrolledWindow()
        yells_scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        yells_scrolled.set_min_content_height(360)
        yells_scrolled.set_vexpand(True)

        self.yells_rows_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.yells_rows_box.add_css_class("yells-panel")
        self.yells_rows_box.set_margin_top(6)
        self.yells_rows_box.set_margin_bottom(6)
        self.yells_rows_box.set_margin_start(6)
        self.yells_rows_box.set_margin_end(6)
        yells_scrolled.set_child(self.yells_rows_box)

        yells_group.add(yells_scrolled)
        yells_box.append(yells_group)

        news_title = self._make_centered_section_title("HorizonXI News")
        news_box.append(news_title)

        news_group = Adw.PreferencesGroup(
            description="Latest articles from HorizonXI. Click an article to open it in your browser.",
        )

        self.news_status_label = Gtk.Label(label="Loading news...")
        self.news_status_label.add_css_class("dim-label")
        self.news_status_label.set_xalign(0)
        self.news_status_label.set_margin_bottom(6)
        news_group.add(self.news_status_label)

        news_scrolled = Gtk.ScrolledWindow()
        news_scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        news_scrolled.set_min_content_height(360)
        news_scrolled.set_vexpand(True)

        self.news_rows_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.news_rows_box.set_margin_top(6)
        self.news_rows_box.set_margin_bottom(6)
        self.news_rows_box.set_margin_start(6)
        self.news_rows_box.set_margin_end(6)
        news_scrolled.set_child(self.news_rows_box)

        news_group.add(news_scrolled)
        news_box.append(news_group)

        friends_title = self._make_centered_section_title("Friends")
        friends_box.append(friends_title)

        friends_group = Adw.PreferencesGroup(
            description="Follow characters by name. This list is local to your launcher.",
        )

        add_friend_button = Gtk.Button(label="Add Friend")
        add_friend_button.add_css_class("suggested-action")
        add_friend_button.connect("clicked", self.on_add_friend_clicked)
        friends_group.add(add_friend_button)

        self.friends_status_label = Gtk.Label(label="Loading friends...")
        self.friends_status_label.add_css_class("dim-label")
        self.friends_status_label.set_xalign(0)
        self.friends_status_label.set_margin_top(6)
        self.friends_status_label.set_margin_bottom(6)
        friends_group.add(self.friends_status_label)

        friends_scrolled = Gtk.ScrolledWindow()
        friends_scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        friends_scrolled.set_min_content_height(360)
        friends_scrolled.set_vexpand(True)

        self.friends_rows_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.friends_rows_box.add_css_class("friends-panel")
        self.friends_rows_box.set_margin_top(6)
        self.friends_rows_box.set_margin_bottom(6)
        self.friends_rows_box.set_margin_start(6)
        self.friends_rows_box.set_margin_end(6)
        friends_scrolled.set_child(self.friends_rows_box)

        friends_group.add(friends_scrolled)
        friends_box.append(friends_group)

        GLib.idle_add(self.render_friends)
        return page

    def refresh_yells_async(self):
        thread = threading.Thread(target=self.fetch_yells, daemon=True)
        thread.start()
        return True

    def refresh_news_async(self):
        thread = threading.Thread(target=self.fetch_news, daemon=True)
        thread.start()
        return True

    def fetch_json_url(self, url, timeout=10):
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "HorizonXI-Linux-Launcher/0.2"},
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    def fetch_yells(self):
        try:
            payload = self.fetch_json_url(HORIZON_YELLS_URL, timeout=10)
            GLib.idle_add(self.apply_yells, payload)
        except Exception as error:
            GLib.idle_add(self.apply_yells_error, str(error))

    def fetch_news(self):
        try:
            payload = self.fetch_json_url(HORIZON_NEWS_URL, timeout=10)
            GLib.idle_add(self.apply_news, payload)
        except Exception as error:
            GLib.idle_add(self.apply_news_error, str(error))

    def clear_box_children(self, box):
        if not box:
            return

        child = box.get_first_child()
        while child is not None:
            next_child = child.get_next_sibling()
            box.remove(child)
            child = next_child

    def apply_yells(self, payload):
        if not self.yells_rows_box:
            return False

        self.clear_box_children(self.yells_rows_box)

        if not isinstance(payload, list):
            self.apply_yells_error("Unexpected yells response.")
            return False

        yells = payload[:40]

        if self.yells_status_label:
            self.yells_status_label.set_text(f"Showing latest {len(yells)} yells.")

        for index, yell in enumerate(yells):
            row = self.create_yell_row(yell)
            self.yells_rows_box.append(row)

            if index < len(yells) - 1:
                separator = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
                separator.add_css_class("yell-separator")
                self.yells_rows_box.append(separator)

        return False

    def apply_yells_error(self, error_message):
        if self.yells_status_label:
            self.yells_status_label.set_text(f"Could not load yells: {error_message}")

        if self.yells_rows_box:
            self.clear_box_children(self.yells_rows_box)

        return False

    def create_yell_row(self, yell):
        speaker = "Unknown"
        message = ""
        date_value = None

        if isinstance(yell, dict):
            speaker = str(yell.get("speaker", yell.get("name", "Unknown")))
            message = str(yell.get("message", yell.get("text", "")))
            date_value = yell.get("date", yell.get("time", None))
        else:
            message = str(yell)

        row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        row.add_css_class("yell-row")
        row.set_margin_top(0)
        row.set_margin_bottom(0)
        row.set_margin_start(0)
        row.set_margin_end(0)

        time_text = html.escape(self.format_api_time(date_value))
        speaker_text = html.escape(speaker)
        message_text = html.escape(message)

        line = Gtk.Label()
        line.set_markup(
            f'<span foreground="#cbd5e1">[{time_text}] </span>'
            f'<span foreground="#e58da0"><b>{speaker_text}:</b></span> '
            f'<span foreground="#f0c6d0">{message_text}</span>'
        )
        line.set_xalign(0)
        line.set_wrap(True)
        line.set_selectable(True)
        row.append(line)

        return row

    def apply_news(self, payload):
        if not self.news_rows_box:
            return False

        self.clear_box_children(self.news_rows_box)

        if not isinstance(payload, list):
            self.apply_news_error("Unexpected news response.")
            return False

        articles = payload[:12]

        if self.news_status_label:
            self.news_status_label.set_text(f"Showing latest {len(articles)} articles.")

        for article in articles:
            row = self.create_news_row(article)
            self.news_rows_box.append(row)

        return False

    def apply_news_error(self, error_message):
        if self.news_status_label:
            self.news_status_label.set_text(f"Could not load news: {error_message}")

        if self.news_rows_box:
            self.clear_box_children(self.news_rows_box)

        return False

    def create_news_row(self, article):
        title = "Untitled"
        excerpt = ""
        print_date = ""
        reading_time = ""
        slug = None

        if isinstance(article, dict):
            title = str(article.get("title", "Untitled"))
            excerpt = str(article.get("excerpt", ""))
            print_date = str(article.get("printDate", ""))
            reading_time = str(article.get("printReadingTime", article.get("readingTime", "")))
            slug = article.get("slug", None)
            if not print_date:
                print_date = self.format_news_date(article.get("date", None))
        else:
            title = str(article)

        url = "https://horizonxi.com/news"
        if slug:
            url = f"https://horizonxi.com/news/{slug}"

        button = Gtk.Button()
        button.set_halign(Gtk.Align.FILL)
        button.connect("clicked", self.on_open_link_clicked, url)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.set_margin_top(8)
        box.set_margin_bottom(8)
        box.set_margin_start(10)
        box.set_margin_end(10)

        title_label = Gtk.Label(label=title)
        title_label.add_css_class("heading")
        title_label.set_xalign(0)
        title_label.set_wrap(True)
        box.append(title_label)

        meta_parts = [part for part in (print_date, reading_time) if part]
        if meta_parts:
            meta = Gtk.Label(label="  •  ".join(meta_parts))
            meta.add_css_class("dim-label")
            meta.set_xalign(0)
            meta.set_wrap(True)
            box.append(meta)

        if excerpt:
            excerpt_label = Gtk.Label(label=excerpt)
            excerpt_label.set_xalign(0)
            excerpt_label.set_wrap(True)
            box.append(excerpt_label)

        button.set_child(box)
        return button

    def format_api_time(self, value):
        if value is None:
            return "Unknown time"

        try:
            timestamp = float(value)
            if timestamp > 100000000000:
                timestamp = timestamp / 1000.0
            dt = datetime.fromtimestamp(timestamp)
            return dt.strftime("%H:%M")
        except Exception:
            return str(value)

    def format_news_date(self, value):
        if not value:
            return ""

        try:
            clean_value = str(value).replace("Z", "+00:00")
            dt = datetime.fromisoformat(clean_value)
            return dt.strftime("%B %-d, %Y")
        except Exception:
            try:
                return datetime.fromisoformat(str(value).split("T")[0]).strftime("%B %-d, %Y")
            except Exception:
                return str(value)

    def load_friends(self):
        self.friend_names = []
        try:
            if FRIENDS_FILE.exists():
                data = json.loads(FRIENDS_FILE.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    self.friend_names = [str(name).strip() for name in data if str(name).strip()]
        except Exception as error:
            print(f"Failed to load friends: {error}")
            self.friend_names = []

    def save_friends(self):
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            FRIENDS_FILE.write_text(json.dumps(self.friend_names, indent=2) + "\n", encoding="utf-8")
        except Exception as error:
            print(f"Failed to save friends: {error}")

    def refresh_friends_async(self):
        thread = threading.Thread(target=self.fetch_friends_data, daemon=True)
        thread.start()
        return True

    def fetch_friends_data(self):
        try:
            characters = []

            # /api/v1/chars only appears to contain online characters, so it is not
            # reliable for validating or refreshing offline friends. Fetch each
            # followed character directly instead.
            for friend_name in list(self.friend_names):
                character = self.fetch_character_by_name(friend_name)
                if character:
                    characters.append(character)

            GLib.idle_add(self.apply_friends_data, characters)
        except Exception as error:
            GLib.idle_add(self.apply_friends_error, str(error))

    def fetch_character_by_name(self, name, timeout=10):
        safe_name = urllib.parse.quote(str(name).strip())
        if not safe_name:
            return None

        payload = self.fetch_json_url(HORIZON_CHAR_URL.format(name=safe_name), timeout=timeout)
        return self.normalize_single_character_payload(payload)

    def normalize_single_character_payload(self, payload):
        if isinstance(payload, dict):
            # Direct character endpoint: usually the character object itself.
            if self.get_character_name(payload):
                return payload

            # Be tolerant of wrappers such as {"data": {...}} or {"character": {...}}.
            for key in ("char", "character", "player", "data", "result"):
                value = payload.get(key)
                if isinstance(value, dict) and self.get_character_name(value):
                    return value

        if isinstance(payload, list) and payload:
            for item in payload:
                if isinstance(item, dict) and self.get_character_name(item):
                    return item

        return None

    def normalize_characters_payload(self, payload):
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]

        if isinstance(payload, dict):
            for key in ("chars", "characters", "players", "data", "results"):
                value = payload.get(key)
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]

            values = list(payload.values())
            if values and all(isinstance(item, dict) for item in values):
                return values

        return []

    def apply_friends_data(self, characters):
        self.characters_cache = characters
        self.characters_by_name = {}

        for character in characters:
            name = self.get_character_name(character)
            if name:
                self.characters_by_name[name.lower()] = character

        self.render_friends()
        return False

    def apply_friends_error(self, error_message):
        if self.friends_status_label:
            self.friends_status_label.set_text(f"Could not refresh friends: {error_message}")
        self.render_friends()
        return False

    def render_friends(self):
        if not self.friends_rows_box:
            return False

        self.clear_box_children(self.friends_rows_box)

        if not self.friend_names:
            if self.friends_status_label:
                self.friends_status_label.set_text("No friends added yet.")

            empty_label = Gtk.Label(label="Add a character to follow their online status and job.")
            empty_label.add_css_class("dim-label")
            empty_label.set_wrap(True)
            empty_label.set_xalign(0)
            self.friends_rows_box.append(empty_label)
            return False

        friend_entries = []
        online_count = 0

        for friend_name in self.friend_names:
            character = self.characters_by_name.get(friend_name.lower())
            is_online = bool(character and self.get_character_online(character))

            if is_online:
                online_count += 1

            display_name = friend_name
            if character:
                display_name = self.get_character_name(character) or friend_name

            friend_entries.append((friend_name, character, display_name, is_online))

        friend_entries.sort(
            key=lambda entry: (
                0 if entry[3] else 1,
                entry[2].lower(),
            )
        )

        for index, (friend_name, character, _display_name, _is_online) in enumerate(friend_entries):
            self.friends_rows_box.append(self.create_friend_row(friend_name, character))

            if index < len(friend_entries) - 1:
                separator = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
                separator.add_css_class("friend-separator")
                self.friends_rows_box.append(separator)

        if self.friends_status_label:
            self.friends_status_label.set_text(f"{online_count}/{len(self.friend_names)} friends online.")

        return False

    def create_friend_row(self, friend_name, character):
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        row.add_css_class("friend-row")
        row.set_margin_top(0)
        row.set_margin_bottom(0)
        row.set_margin_start(0)
        row.set_margin_end(0)

        info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        info_box.set_hexpand(True)
        info_box.set_valign(Gtk.Align.CENTER)

        display_name = friend_name
        online = False
        job_string = "Unknown job"

        if character:
            display_name = self.get_character_name(character) or friend_name
            online = self.get_character_online(character)
            job_string = self.get_character_jobstring(character)
        elif self.characters_by_name:
            job_string = "Character not found"

        status_dot = "🟢" if online else "⚫"
        status_word = "Online" if online else "Offline"

        name_label = Gtk.Label()
        name_label.set_markup(f"<b>{html.escape(display_name)}</b>")
        name_label.set_xalign(0)
        name_label.set_wrap(True)
        info_box.append(name_label)

        detail_label = Gtk.Label(label=f"{status_dot} {status_word} • {job_string}")
        detail_label.add_css_class("dim-label")
        detail_label.set_xalign(0)
        detail_label.set_wrap(True)
        info_box.append(detail_label)

        remove_button = Gtk.Button(label="Remove")
        remove_button.add_css_class("flat")
        remove_button.add_css_class("friend-remove-button")
        remove_button.set_valign(Gtk.Align.CENTER)
        remove_button.connect("clicked", self.on_remove_friend_clicked, friend_name)

        row.append(info_box)
        row.append(remove_button)
        return row

    def get_character_name(self, character):
        for key in ("charname", "name", "character", "player", "playerName"):
            value = character.get(key)
            if value:
                return str(value)
        return ""

    def get_character_online(self, character):
        for key in ("isOnline", "online", "is_online"):
            if key in character:
                value = character.get(key)
                if isinstance(value, str):
                    return value.lower() in ("true", "1", "yes", "online")
                return bool(value)

        status = str(character.get("status", "")).lower()
        return status == "online"

    def get_character_jobstring(self, character):
        for key in ("jobString", "jobstring", "job_string", "jobs", "job"):
            value = character.get(key)
            if value not in (None, ""):
                return str(value)

        main_job = character.get("mainJob", character.get("main_job", character.get("jobName", character.get("mjob"))))
        main_level = character.get("mainLevel", character.get("main_level", character.get("jobLevel", character.get("mlvl"))))
        sub_job = character.get("subJob", character.get("sub_job", character.get("subJobName", character.get("sjob"))))
        sub_level = character.get("subLevel", character.get("sub_level", character.get("subJobLevel", character.get("slvl"))))

        if main_job and main_level and sub_job and sub_level:
            return f"{main_job} {main_level}/{sub_job} {sub_level}"

        if main_job and main_level:
            return f"{main_job} {main_level}"

        return "Unknown job"

    def get_character_location(self, character):
        for key in (
            "zoneName", "zone_name", "currentZone", "current_zone",
            "location", "area", "zone", "region", "pos_zone",
        ):
            value = character.get(key)
            if value not in (None, ""):
                if isinstance(value, int):
                    return f"Zone {value}"
                return str(value)
        return "Unknown location"

    def on_add_friend_clicked(self, button):
        dialog = Adw.MessageDialog(
            transient_for=self.window,
            heading="Add Friend",
            body="Enter a HorizonXI character name to follow.",
        )
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("add", "Add Friend")
        dialog.set_default_response("add")
        dialog.set_close_response("cancel")

        entry = Gtk.Entry()
        entry.set_placeholder_text("Character name")
        entry.set_activates_default(True)
        entry.set_margin_top(8)
        dialog.set_extra_child(entry)
        dialog.connect("response", self.on_add_friend_response, entry)
        dialog.present()
        entry.grab_focus()

    def on_add_friend_response(self, dialog, response, entry):
        if response != "add":
            return

        name = entry.get_text().strip()
        if not name:
            self.show_friend_message("Enter a character name first.")
            return

        self.add_friend_by_name(name)

    def add_friend_by_name(self, name):
        self.show_friend_message("Checking character...")

        def worker():
            try:
                character = self.fetch_character_by_name(name, timeout=10)
                GLib.idle_add(self.finish_add_friend_by_name, name, character)
            except Exception:
                GLib.idle_add(
                    self.show_friend_message,
                    f"Character '{name}' does not exist."
                )

        threading.Thread(target=worker, daemon=True).start()

    def finish_add_friend_by_name(self, name, character=None):
        if not character:
            self.show_friend_message(f"Character '{name}' does not exist.")
            return False

        canonical_name = self.get_character_name(character) or name
        if canonical_name.lower() in [existing.lower() for existing in self.friend_names]:
            self.show_friend_message(f"{canonical_name} is already in your friends list.")
            return False

        self.friend_names.append(canonical_name)
        self.friend_names.sort(key=str.lower)
        self.characters_by_name[canonical_name.lower()] = character
        self.save_friends()
        self.show_friend_message(f"Added {canonical_name}.")
        self.render_friends()
        return False

    def on_remove_friend_clicked(self, button, friend_name):
        self.friend_names = [name for name in self.friend_names if name.lower() != friend_name.lower()]
        self.save_friends()
        self.show_friend_message(f"Removed {friend_name}.")
        self.render_friends()

    def show_friend_message(self, message, seconds=3):
        if self.friends_status_label:
            self.friends_status_label.set_text(message)
            GLib.timeout_add_seconds(seconds, self.render_friends)
        return False

    def build_addons_page(self):
        page = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=24,
            homogeneous=True,
        )

        left_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        right_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)

        addons_group = Adw.PreferencesGroup(
            title="Addons",
            description=(
                "Detected dynamically from Game/addons. Toggles edit "
                "Game/scripts/default.txt between the Horizon addon markers."
            ),
        )

        addons_button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        addons_button_box.set_homogeneous(True)

        refresh_button = Gtk.Button(label="Refresh Addons")
        refresh_button.connect("clicked", self.on_refresh_addons_clicked)
        addons_button_box.append(refresh_button)
        self.addons_refresh_button = refresh_button

        reset_addons_button = Gtk.Button(label="Reset Addons to Default")
        reset_addons_button.connect("clicked", self.on_reset_addons_clicked)
        addons_button_box.append(reset_addons_button)

        addons_group.add(addons_button_box)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_min_content_height(300)
        scrolled.set_vexpand(True)

        self.addons_rows_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=0,
        )
        scrolled.set_child(self.addons_rows_box)

        left_box.append(addons_group)
        left_box.append(scrolled)

        plugins_group = Adw.PreferencesGroup(
            title="Plugins / Extensions",
            description=(
                "Detected dynamically from Game/plugins and Game/polplugins. "
                "Plugin toggles edit Game/scripts/default.txt; POL plugin toggles edit ashita.ini."
            ),
        )

        extensions_button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        extensions_button_box.set_homogeneous(True)

        extensions_refresh = Gtk.Button(label="Refresh Plugins / Extensions")
        extensions_refresh.connect("clicked", self.on_refresh_extensions_clicked)
        extensions_button_box.append(extensions_refresh)
        self.extensions_refresh_button = extensions_refresh

        reset_extensions_button = Gtk.Button(label="Reset Plugins / Extensions")
        reset_extensions_button.connect("clicked", self.on_reset_extensions_clicked)
        extensions_button_box.append(reset_extensions_button)

        plugins_group.add(extensions_button_box)

        plugins_scrolled = Gtk.ScrolledWindow()
        plugins_scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        plugins_scrolled.set_min_content_height(180)
        plugins_scrolled.set_vexpand(True)

        self.plugins_rows_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=0,
        )
        plugins_scrolled.set_child(self.plugins_rows_box)

        polplugins_scrolled = Gtk.ScrolledWindow()
        polplugins_scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        polplugins_scrolled.set_min_content_height(110)
        polplugins_scrolled.set_vexpand(True)

        self.polplugins_rows_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=0,
        )
        polplugins_scrolled.set_child(self.polplugins_rows_box)

        right_box.append(plugins_group)
        right_box.append(plugins_scrolled)
        right_box.append(polplugins_scrolled)

        page.append(left_box)
        page.append(right_box)

        GLib.idle_add(self.refresh_addons_list)
        GLib.idle_add(self.refresh_extensions_list)

        return page

    def refresh_addons_list(self):
        if not self.addons_rows_box:
            return False

        child = self.addons_rows_box.get_first_child()
        while child is not None:
            next_child = child.get_next_sibling()
            self.addons_rows_box.remove(child)
            child = next_child

        if not self.addon_manager.is_available():
            group = Adw.PreferencesGroup(title="Addons unavailable")
            row = Adw.ActionRow(title="Game install not found")
            row.set_subtitle("Install HorizonXI first, then refresh this tab.")
            group.add(row)
            self.addons_rows_box.append(group)
            return False

        addons = self.addon_manager.scan_addons()

        if not addons:
            group = Adw.PreferencesGroup(title="No addons found")
            row = Adw.ActionRow(title="No addon folders detected")
            row.set_subtitle("Expected addons inside Game/addons/<addon>/<addon>.lua")
            group.add(row)
            self.addons_rows_box.append(group)
            return False

        group = Adw.PreferencesGroup(title=f"Detected Addons ({len(addons)})")

        for addon in addons:
            row = Adw.SwitchRow(title=addon.name)
            row.set_subtitle(addon.description)
            row.set_active(addon.enabled)
            row.connect("notify::active", self.on_addon_switch_toggled, addon.name)
            group.add(row)

        self.addons_rows_box.append(group)
        return False

    def on_refresh_addons_clicked(self, button):
        self.refresh_addons_list()
        if self.status_label:
            self.status_label.set_text("Addon list refreshed.")

    def on_reset_addons_clicked(self, button):
        try:
            self.addon_manager.reset_addons_to_default()
            self.refresh_addons_list()
            if self.status_label:
                self.status_label.set_text("Addons reset to installed defaults.")
        except Exception as error:
            if self.status_label:
                self.status_label.set_text(f"Failed to reset addons: {error}")

    def on_addon_switch_toggled(self, row, pspec, addon_name):
        try:
            enabled = row.get_active()
            self.addon_manager.set_addon_enabled(addon_name, enabled)
            if self.status_label:
                state = "enabled" if enabled else "disabled"
                self.status_label.set_text(f"Addon {addon_name} {state}.")
        except Exception as error:
            if self.status_label:
                self.status_label.set_text(f"Failed to update addon {addon_name}: {error}")
            # Refresh to return the UI to the file-backed state.
            GLib.idle_add(self.refresh_addons_list)

    def refresh_extensions_list(self):
        self.refresh_plugins_list()
        self.refresh_polplugins_list()
        return False

    def refresh_plugins_list(self):
        if not self.plugins_rows_box:
            return False

        child = self.plugins_rows_box.get_first_child()
        while child is not None:
            next_child = child.get_next_sibling()
            self.plugins_rows_box.remove(child)
            child = next_child

        if not self.plugin_manager.is_available():
            group = Adw.PreferencesGroup(title="Plugins unavailable")
            row = Adw.ActionRow(title="Game install not found")
            row.set_subtitle("Install HorizonXI first, then refresh this tab.")
            group.add(row)
            self.plugins_rows_box.append(group)
            return False

        plugins = self.plugin_manager.scan_plugins()

        if not plugins:
            group = Adw.PreferencesGroup(title="No Ashita plugins found")
            row = Adw.ActionRow(title="No plugin DLLs detected")
            row.set_subtitle("Expected plugins inside Game/plugins/*.dll")
            group.add(row)
            self.plugins_rows_box.append(group)
            return False

        group = Adw.PreferencesGroup(title=f"Ashita Plugins ({len(plugins)})")

        for plugin in plugins:
            row = Adw.SwitchRow(title=plugin.name)
            row.set_subtitle(plugin.source)
            row.set_active(plugin.enabled)
            row.connect("notify::active", self.on_plugin_switch_toggled, plugin.name)
            group.add(row)

        self.plugins_rows_box.append(group)
        return False

    def refresh_polplugins_list(self):
        if not self.polplugins_rows_box:
            return False

        child = self.polplugins_rows_box.get_first_child()
        while child is not None:
            next_child = child.get_next_sibling()
            self.polplugins_rows_box.remove(child)
            child = next_child

        if not self.plugin_manager.is_available():
            return False

        polplugins = self.plugin_manager.scan_polplugins()

        if not polplugins:
            group = Adw.PreferencesGroup(title="No PlayOnline plugins found")
            row = Adw.ActionRow(title="No POL plugin entries detected")
            row.set_subtitle("Expected entries in Game/polplugins or config/boot/ashita.ini")
            group.add(row)
            self.polplugins_rows_box.append(group)
            return False

        group = Adw.PreferencesGroup(title=f"PlayOnline Plugins ({len(polplugins)})")

        for plugin in polplugins:
            row = Adw.SwitchRow(title=plugin.name)
            row.set_subtitle("config/boot/ashita.ini [ashita.polplugins]")
            row.set_active(plugin.enabled)
            row.connect("notify::active", self.on_polplugin_switch_toggled, plugin.name)
            group.add(row)

        self.polplugins_rows_box.append(group)
        return False

    def on_refresh_extensions_clicked(self, button):
        self.refresh_extensions_list()
        if self.status_label:
            self.status_label.set_text("Plugin / extension list refreshed.")

    def on_reset_extensions_clicked(self, button):
        try:
            self.plugin_manager.reset_plugins_to_default()
            self.refresh_extensions_list()
            if self.status_label:
                self.status_label.set_text("Plugins / extensions reset to installed defaults.")
        except Exception as error:
            if self.status_label:
                self.status_label.set_text(f"Failed to reset plugins / extensions: {error}")

    def on_plugin_switch_toggled(self, row, pspec, plugin_name):
        try:
            enabled = row.get_active()
            self.plugin_manager.set_plugin_enabled(plugin_name, enabled)
            if self.status_label:
                state = "enabled" if enabled else "disabled"
                self.status_label.set_text(f"Plugin {plugin_name} {state}.")
        except Exception as error:
            if self.status_label:
                self.status_label.set_text(f"Failed to update plugin {plugin_name}: {error}")
            GLib.idle_add(self.refresh_extensions_list)

    def on_polplugin_switch_toggled(self, row, pspec, plugin_name):
        try:
            enabled = row.get_active()
            self.plugin_manager.set_polplugin_enabled(plugin_name, enabled)
            if self.status_label:
                state = "enabled" if enabled else "disabled"
                self.status_label.set_text(f"PlayOnline plugin {plugin_name} {state}.")
        except Exception as error:
            if self.status_label:
                self.status_label.set_text(f"Failed to update PlayOnline plugin {plugin_name}: {error}")
            GLib.idle_add(self.refresh_extensions_list)

    def build_settings_page(self):
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)

        settings_stack = Gtk.Stack()
        settings_stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        settings_stack.set_vhomogeneous(False)
        settings_stack.set_hhomogeneous(False)
        settings_stack.set_vexpand(False)
        self.settings_stack = settings_stack

        switcher = Gtk.StackSwitcher()
        switcher.set_stack(settings_stack)
        switcher.set_halign(Gtk.Align.CENTER)
        outer.append(switcher)

        settings_stack.add_titled(self.build_general_settings_page(), "general", "General")
        settings_stack.add_titled(self.build_graphics_settings_page(), "graphics", "Graphics")
        settings_stack.add_titled(self.build_tools_settings_page(), "tools", "Tools")

        outer.append(settings_stack)

        GLib.idle_add(self.load_settings_ui)
        return outer

    def _make_centered_section_title(self, text):
        label = Gtk.Label(label=text)
        label.add_css_class("heading")
        label.set_halign(Gtk.Align.CENTER)
        label.set_margin_bottom(8)
        return label

    def _make_button_stack(self, width=360, spacing=8):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=spacing)
        box.set_halign(Gtk.Align.CENTER)
        box.set_margin_top(8)
        box.set_margin_bottom(8)
        return box

    def _add_stacked_button(self, box, label, callback, css_class=None, width=360):
        button = Gtk.Button(label=label)
        button.set_size_request(width, -1)
        if css_class:
            button.add_css_class(css_class)
        button.connect("clicked", callback)
        box.append(button)
        return button

    def build_general_settings_page(self):
        page = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=24, homogeneous=True)

        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        page.append(left)
        page.append(right)

        general_group = Adw.PreferencesGroup(title="General")
        self._add_switch_setting(general_group, "hardware_mouse", "Hardware Mouse")
        self._add_switch_setting(general_group, "play_opening_movie", "Play Opening Movie")
        self._add_switch_setting(general_group, "sound", "Sound")
        self._add_switch_setting(general_group, "always_play_sound", "Always Play Sound")
        self._add_spin_setting(general_group, "max_sounds", "Max # of Sounds", 12, 20, 1)
        self._add_spin_setting(general_group, "gamma", "Gamma", -1.0, 1.0, 0.05, digits=2)
        self._add_combo_setting(general_group, "language", "Language", ["English", "Japanese"])
        left.append(general_group)

        resolution_group = Adw.PreferencesGroup(
            title="Resolution",
            description="Window is the game window size, background is the 3D render size, menu is the UI/menu size.",
        )
        self._add_resolution_setting(resolution_group, "window", "Window Resolution")
        self._add_resolution_setting(resolution_group, "background", "Background Resolution")
        self._add_resolution_setting(resolution_group, "menu", "Menu Resolution")

        resolution_buttons_box = self._make_button_stack()
        self._add_stacked_button(
            resolution_buttons_box,
            "Use Monitor Native Resolution",
            self.on_use_native_resolution_clicked,
        )
        resolution_group.add(resolution_buttons_box)

        right.append(resolution_group)

        window_group = Adw.PreferencesGroup(title="Window")
        self._add_combo_setting(
            window_group,
            "window_mode",
            "Window Mode",
            ["Fullscreen", "Window", "Fullscreen Windowed", "Borderless Windowed"],
        )
        right.append(window_group)

        actions_group = Adw.PreferencesGroup(title="Settings Actions")
        actions_buttons_box = self._make_button_stack()
        self._add_stacked_button(
            actions_buttons_box,
            "Save Settings",
            self.on_save_settings_clicked,
            "suggested-action",
        )
        self._add_stacked_button(
            actions_buttons_box,
            "Reset Settings to Default",
            self.on_reset_settings_clicked,
        )
        actions_group.add(actions_buttons_box)
        right.append(actions_group)

        return page

    def build_graphics_settings_page(self):
        page = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=24, homogeneous=True)
        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        page.append(left)
        page.append(right)

        toggles_group = Adw.PreferencesGroup(title="Graphics Toggles")
        self._add_switch_setting(toggles_group, "graphics_stabilization", "Graphics Stabilization")
        self._add_switch_setting(toggles_group, "map_compression", "Map Compression")
        self._add_switch_setting(toggles_group, "bump_mapping", "Bump Mapping")
        self._add_switch_setting(toggles_group, "maintain_aspect_ratio", "Maintain Aspect Ratio")
        self._add_switch_setting(toggles_group, "lcd_mode", "3D LCD Mode")
        left.append(toggles_group)

        quality_group = Adw.PreferencesGroup(title="Quality")
        self._add_spin_setting(quality_group, "environment", "Environment", 0, 2, 1)
        self._add_spin_setting(quality_group, "textures", "Textures", 0, 2, 1)
        self._add_spin_setting(quality_group, "fonts", "Fonts", 0, 2, 1)
        self._add_spin_setting(quality_group, "mip_mapping", "Mip Mapping", 0, 6, 1)
        right.append(quality_group)

        actions_group = Adw.PreferencesGroup(title="Settings Actions")
        actions_buttons_box = self._make_button_stack()
        self._add_stacked_button(
            actions_buttons_box,
            "Save Settings",
            self.on_save_settings_clicked,
            "suggested-action",
        )
        self._add_stacked_button(
            actions_buttons_box,
            "Reset Settings to Default",
            self.on_reset_settings_clicked,
        )
        actions_group.add(actions_buttons_box)
        right.append(actions_group)

        return page

    def build_tools_settings_page(self):
        page = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=24, homogeneous=True)

        tools_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        page.append(tools_box)

        tools_box.append(self._make_centered_section_title("Tools"))
        tools_group = Adw.PreferencesGroup()

        tools_buttons_box = self._make_button_stack()

        self.gamepad_button = Gtk.Button(label="Open Gamepad Config")
        self.gamepad_button.set_size_request(360, -1)
        self.gamepad_button.connect("clicked", self.on_open_gamepad_config_clicked)
        tools_buttons_box.append(self.gamepad_button)

        self.launch_button = Gtk.Button(label="Open Official Launcher")
        self.launch_button.set_size_request(360, -1)
        self.launch_button.connect("clicked", self.on_launch_clicked)
        tools_buttons_box.append(self.launch_button)

        self.open_folder_button = Gtk.Button(label="Open Game Folder")
        self.open_folder_button.set_size_request(360, -1)
        self.open_folder_button.connect("clicked", self.on_open_game_folder_clicked)
        tools_buttons_box.append(self.open_folder_button)

        self.backup_macros_button = Gtk.Button(label="Backup Macros")
        self.backup_macros_button.set_size_request(360, -1)
        self.backup_macros_button.connect("clicked", self.on_backup_macros_clicked)
        tools_buttons_box.append(self.backup_macros_button)

        self.install_button = Gtk.Button(label="Repair Installation")
        self.install_button.set_size_request(360, -1)
        self.install_button.add_css_class("suggested-action")
        self.install_button.connect("clicked", self.on_install_clicked)
        tools_buttons_box.append(self.install_button)

        tools_group.add(tools_buttons_box)
        tools_box.append(tools_group)

        tools_box.append(self._make_centered_section_title("Danger Zone"))
        danger_group = Adw.PreferencesGroup()

        danger_box = self._make_button_stack()

        self.reset_button = Gtk.Button(label="Nuclear Reset")
        self.reset_button.set_size_request(360, -1)
        self.reset_button.add_css_class("destructive-action")
        self.reset_button.connect("clicked", self.on_nuclear_reset_clicked)
        danger_box.append(self.reset_button)

        danger_group.add(danger_box)

        danger_note = Gtk.Label(
            label=(
                "Deletes the managed Wine prefix, game files, official launcher, "
                "managed Proton files, downloads, logs, and saved credentials. "
                "The Linux launcher app/project is not deleted."
            )
        )
        danger_note.set_wrap(True)
        danger_note.set_xalign(0)
        danger_note.add_css_class("dim-label")
        danger_note.set_margin_top(4)
        danger_group.add(danger_note)

        tools_box.append(danger_group)

        return page

    def _add_switch_setting(self, group, key, title):
        row = Adw.SwitchRow(title=title)
        group.add(row)
        self.settings_controls[key] = row
        return row

    def _add_spin_setting(self, group, key, title, lower, upper, step, digits=0):
        row = Adw.ActionRow(title=title)
        adjustment = Gtk.Adjustment(value=lower, lower=lower, upper=upper, step_increment=step, page_increment=step * 4)
        spin = Gtk.SpinButton(adjustment=adjustment)
        spin.set_numeric(True)
        spin.set_digits(digits)
        spin.set_valign(Gtk.Align.CENTER)
        row.add_suffix(spin)
        row.set_activatable_widget(spin)
        group.add(row)
        self.settings_controls[key] = spin
        return spin

    def _add_combo_setting(self, group, key, title, options):
        row = Adw.ComboRow(title=title)
        model = Gtk.StringList.new(options)
        row.set_model(model)
        row.set_selected(0)
        group.add(row)
        self.settings_controls[key] = (row, options)
        return row

    def _add_resolution_setting(self, group, key_prefix, title):
        row = Adw.ActionRow(title=title)
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)

        width_adjustment = Gtk.Adjustment(value=1920, lower=320, upper=16384, step_increment=1, page_increment=100)
        width_spin = Gtk.SpinButton(adjustment=width_adjustment)
        width_spin.set_numeric(True)
        width_spin.set_width_chars(5)
        width_spin.set_valign(Gtk.Align.CENTER)
        width_spin.set_vexpand(False)

        by_label = Gtk.Label(label="×")
        by_label.add_css_class("dim-label")

        height_adjustment = Gtk.Adjustment(value=1080, lower=240, upper=16384, step_increment=1, page_increment=100)
        height_spin = Gtk.SpinButton(adjustment=height_adjustment)
        height_spin.set_numeric(True)
        height_spin.set_width_chars(5)
        height_spin.set_valign(Gtk.Align.CENTER)
        height_spin.set_vexpand(False)

        box.set_valign(Gtk.Align.CENTER)
        box.set_vexpand(False)
        box.append(width_spin)
        box.append(by_label)
        box.append(height_spin)
        row.add_suffix(box)
        row.set_activatable_widget(width_spin)
        group.add(row)

        self.settings_controls[f"{key_prefix}_width"] = width_spin
        self.settings_controls[f"{key_prefix}_height"] = height_spin

    def load_settings_ui(self):
        if not self.settings_manager.is_available():
            return False
        try:
            self.settings_manager.ensure_default_snapshot()
            settings = self.settings_manager.read_settings()
            self._set_switch("hardware_mouse", settings.hardware_mouse)
            self._set_switch("play_opening_movie", settings.play_opening_movie)
            self._set_switch("sound", settings.sound)
            self._set_switch("always_play_sound", settings.always_play_sound)
            self._set_spin("max_sounds", settings.max_sounds)
            self._set_spin("gamma", settings.gamma)
            self._set_combo("language", settings.language)
            self._set_combo("window_mode", settings.window_mode)
            self._set_spin("window_width", settings.window_width)
            self._set_spin("window_height", settings.window_height)
            self._set_spin("background_width", settings.background_width)
            self._set_spin("background_height", settings.background_height)
            self._set_spin("menu_width", settings.menu_width)
            self._set_spin("menu_height", settings.menu_height)
            self._set_switch("graphics_stabilization", settings.graphics_stabilization)
            self._set_switch("map_compression", settings.map_compression)
            self._set_switch("bump_mapping", settings.bump_mapping)
            self._set_switch("maintain_aspect_ratio", settings.maintain_aspect_ratio)
            self._set_switch("lcd_mode", settings.lcd_mode)
            self._set_spin("environment", settings.environment)
            self._set_spin("textures", settings.textures)
            self._set_spin("fonts", settings.fonts)
            self._set_spin("mip_mapping", settings.mip_mapping)
        except Exception as error:
            if self.status_label:
                self.status_label.set_text(f"Failed to load settings: {error}")
        return False

    def collect_settings_from_ui(self):
        return GameSettings(
            hardware_mouse=self._get_switch("hardware_mouse"),
            play_opening_movie=self._get_switch("play_opening_movie"),
            sound=self._get_switch("sound"),
            always_play_sound=self._get_switch("always_play_sound"),
            max_sounds=int(self._get_spin("max_sounds")),
            language=self._get_combo("language"),
            window_mode=self._get_combo("window_mode"),
            window_width=int(self._get_spin("window_width")),
            window_height=int(self._get_spin("window_height")),
            background_width=int(self._get_spin("background_width")),
            background_height=int(self._get_spin("background_height")),
            menu_width=int(self._get_spin("menu_width")),
            menu_height=int(self._get_spin("menu_height")),
            gamma=float(self._get_spin("gamma")),
            graphics_stabilization=self._get_switch("graphics_stabilization"),
            map_compression=self._get_switch("map_compression"),
            bump_mapping=self._get_switch("bump_mapping"),
            maintain_aspect_ratio=self._get_switch("maintain_aspect_ratio"),
            lcd_mode=self._get_switch("lcd_mode"),
            environment=int(self._get_spin("environment")),
            textures=int(self._get_spin("textures")),
            fonts=int(self._get_spin("fonts")),
            mip_mapping=int(self._get_spin("mip_mapping")),
        )

    def on_use_native_resolution_clicked(self, button):
        resolution = self.get_monitor_native_resolution()

        if resolution is None:
            if self.status_label:
                self.status_label.set_text("Could not detect monitor resolution.")
            return

        width, height = resolution

        for key in ("window", "background", "menu"):
            self._set_spin(f"{key}_width", width)
            self._set_spin(f"{key}_height", height)

        if self.status_label:
            self.status_label.set_text(
                f"Set window, background, and menu resolutions to {width}×{height}."
            )

    def get_monitor_native_resolution(self):
        display = None

        try:
            if self.window:
                display = self.window.get_display()
        except Exception:
            display = None

        if display is None:
            display = Gdk.Display.get_default()

        if display is None:
            return None

        monitor = None

        try:
            if self.window and self.window.get_surface():
                monitor = display.get_monitor_at_surface(self.window.get_surface())
        except Exception:
            monitor = None

        if monitor is None:
            try:
                monitors = display.get_monitors()
                if monitors and monitors.get_n_items() > 0:
                    monitor = monitors.get_item(0)
            except Exception:
                monitor = None

        if monitor is None:
            return None

        try:
            geometry = monitor.get_geometry()
            scale_factor = monitor.get_scale_factor()
            width = int(geometry.width * scale_factor)
            height = int(geometry.height * scale_factor)
        except Exception:
            return None

        if width <= 0 or height <= 0:
            return None

        return width, height

    def on_save_settings_clicked(self, button):
        try:
            settings = self.collect_settings_from_ui()
            self.settings_manager.write_settings(settings)
            self.status_label.set_text("Settings saved. Restart the game for changes to apply.")
        except Exception as error:
            self.status_label.set_text(f"Failed to save settings: {error}")

    def on_reset_settings_clicked(self, button):
        try:
            self.settings_manager.reset_to_default()
            self.load_settings_ui()
            self.status_label.set_text("Settings reset to installed defaults.")
        except Exception as error:
            self.status_label.set_text(f"Failed to reset settings: {error}")

    def on_open_gamepad_config_clicked(self, button):
        try:
            self.settings_manager.open_gamepad_config()
            self.status_label.set_text("Gamepad config started.")
        except Exception as error:
            self.status_label.set_text(f"Failed to open gamepad config: {error}")

    def _set_switch(self, key, value):
        control = self.settings_controls.get(key)
        if control:
            control.set_active(bool(value))

    def _get_switch(self, key):
        control = self.settings_controls.get(key)
        return bool(control.get_active()) if control else False

    def _set_spin(self, key, value):
        control = self.settings_controls.get(key)
        if control:
            control.set_value(float(value))

    def _get_spin(self, key):
        control = self.settings_controls.get(key)
        return control.get_value() if control else 0

    def _set_combo(self, key, value):
        packed = self.settings_controls.get(key)
        if not packed:
            return
        row, options = packed
        try:
            row.set_selected(options.index(value))
        except ValueError:
            row.set_selected(0)

    def _get_combo(self, key):
        packed = self.settings_controls.get(key)
        if not packed:
            return ""
        row, options = packed
        selected = row.get_selected()
        if 0 <= selected < len(options):
            return options[selected]
        return options[0]

    def get_display_game_status_text(self):
        game_status_text = self.installer.get_game_status_text()

        if self.game_update_available and self.game_update_details:
            installed = self.game_update_details.get("installed_marketing_version") or self.game_update_details.get("installed_version")
            latest = self.game_update_details.get("latest_marketing_version") or self.game_update_details.get("latest_version")
            if installed and latest:
                return f"🎮 Version {installed} installed — update {latest} available"
            return "🎮 Update available"

        if self.game_update_check_in_progress and self.installer.is_game_installed():
            if "installed" in game_status_text.lower():
                return f"🎮 {game_status_text} — checking for updates..."
            return "🎮 Checking for updates..."

        if self.game_update_check_failed and self.installer.is_game_installed():
            if "installed" in game_status_text.lower():
                return f"🎮 {game_status_text} — update check failed"
            return "🎮 Update check failed"

        if "installed" in game_status_text.lower():
            return f"🎮 {game_status_text}"
        if "missing" in game_status_text.lower():
            return f"❌ {game_status_text}"
        return game_status_text

    def refresh_game_update_status_async(self):
        if self.operation_in_progress or self.game_update_check_in_progress:
            return False

        if not self.installer.is_game_installed():
            self.game_update_available = False
            self.game_update_check_failed = False
            self.game_update_details = None
            self.refresh_status()
            return False

        self.game_update_check_in_progress = True
        self.game_update_check_failed = False
        self.refresh_status()

        def worker():
            try:
                details = self.installer.check_game_update_available()
                GLib.idle_add(self.apply_game_update_status, details)
            except Exception as error:
                GLib.idle_add(self.apply_game_update_status_error, str(error))

        threading.Thread(target=worker, daemon=True).start()
        return False

    def apply_game_update_status(self, details):
        self.game_update_check_in_progress = False
        self.game_update_check_failed = False
        self.game_update_details = details if isinstance(details, dict) else None
        self.game_update_available = bool(self.game_update_details and self.game_update_details.get("update_available"))

        if self.status_label and not self.operation_in_progress:
            if self.game_update_available:
                latest = self.game_update_details.get("latest_marketing_version") or self.game_update_details.get("latest_version")
                self.status_label.set_text(f"HorizonXI game update {latest} is available.")
            else:
                self.status_label.set_text("Ready")

        self.refresh_status()
        return False

    def apply_game_update_status_error(self, error_message):
        self.game_update_check_in_progress = False
        self.game_update_check_failed = True
        self.game_update_available = False
        self.game_update_details = None

        if self.status_label and not self.operation_in_progress:
            self.status_label.set_text(f"Could not check for game updates: {error_message}")

        self.refresh_status()
        return False

    def refresh_status(self):
        proton_installed = self.proton.is_installed()
        game_installed = self.installer.is_game_installed()
        official_launcher_installed = self.installer.is_official_launcher_installed()

        self.proton_status.set_subtitle("✅ Installed" if proton_installed else "❌ Missing")
        game_status_text = self.get_display_game_status_text()
        self.game_status.set_subtitle(game_status_text)

        if self.gamepad_button:
            self.gamepad_button.set_sensitive(game_installed and not self.operation_in_progress)

        if self.launch_button:
            self.launch_button.set_sensitive(
                proton_installed and official_launcher_installed and not self.operation_in_progress
            )

        if self.open_folder_button:
            self.open_folder_button.set_sensitive(game_installed and not self.operation_in_progress)

        if self.backup_macros_button:
            self.backup_macros_button.set_sensitive(game_installed and not self.operation_in_progress)

        if self.install_button:
            self.install_button.set_sensitive(not self.operation_in_progress)

        if self.reset_button:
            self.reset_button.set_sensitive(not self.operation_in_progress)

        self.refresh_main_action_button()

    def get_main_action_state(self):
        if self.operation_in_progress:
            return MAIN_ACTION_BUSY

        if not self.installer.is_game_installed():
            return MAIN_ACTION_INSTALL

        if self.game_update_check_in_progress:
            return MAIN_ACTION_CHECKING_UPDATE

        if self.game_update_check_failed:
            return MAIN_ACTION_UPDATE_CHECK_FAILED

        if self.game_update_available:
            return MAIN_ACTION_UPDATE

        if not self.server_online:
            return MAIN_ACTION_MAINTENANCE

        username = self.username_entry.get_text().strip() if self.username_entry else ""
        password = self.password_entry.get_text() if self.password_entry else ""

        if not username or not password:
            return MAIN_ACTION_LOGIN

        return MAIN_ACTION_LAUNCH

    def set_main_button_style(self, css_class=None):
        if not self.launch_game_button:
            return

        for class_name in ("suggested-action", "destructive-action", "update-action"):
            try:
                self.launch_game_button.remove_css_class(class_name)
            except Exception:
                pass

        if css_class:
            try:
                self.launch_game_button.add_css_class(css_class)
            except Exception:
                pass

    def refresh_main_action_button(self):
        if not self.launch_game_button:
            return

        state = self.get_main_action_state()
        self.main_action_state = state

        if state == MAIN_ACTION_BUSY:
            self.set_main_button_style()
            self.launch_game_button.set_label("Working...")
            self.launch_game_button.set_sensitive(False)
        elif state == MAIN_ACTION_INSTALL:
            self.set_main_button_style("suggested-action")
            self.launch_game_button.set_label("Install Game")
            self.launch_game_button.set_sensitive(True)
        elif state == MAIN_ACTION_CHECKING_UPDATE:
            self.set_main_button_style()
            self.launch_game_button.set_label("Checking for Updates...")
            self.launch_game_button.set_sensitive(False)
        elif state == MAIN_ACTION_UPDATE_CHECK_FAILED:
            self.set_main_button_style()
            self.launch_game_button.set_label("Update Check Failed")
            self.launch_game_button.set_sensitive(False)
        elif state == MAIN_ACTION_UPDATE:
            self.set_main_button_style("update-action")
            self.launch_game_button.set_label("Update Game")
            self.launch_game_button.set_sensitive(True)
        elif state == MAIN_ACTION_MAINTENANCE:
            self.set_main_button_style()
            self.launch_game_button.set_label("Server Maintenance")
            self.launch_game_button.set_sensitive(False)
        elif state == MAIN_ACTION_LOGIN:
            self.set_main_button_style("suggested-action")
            self.launch_game_button.set_label("Log In")
            self.launch_game_button.set_sensitive(True)
        else:
            self.set_main_button_style("suggested-action")
            self.launch_game_button.set_label("Launch Game")
            self.launch_game_button.set_sensitive(True)

    def set_operation_in_progress(self, in_progress):
        self.operation_in_progress = in_progress
        self.refresh_status()

    def update_progress(self, message, fraction=None):
        if self.status_label:
            self.status_label.set_text(message)

        if self.progress_bar:
            if fraction is None:
                self.progress_bar.pulse()
            else:
                safe_fraction = max(0.0, min(1.0, float(fraction)))
                self.progress_bar.set_fraction(safe_fraction)

            self.progress_bar.set_text(message)

        return False

    def load_saved_credentials(self):
        self.loading_saved_credentials = True

        try:
            if CREDENTIALS_FILE.exists():
                data = json.loads(CREDENTIALS_FILE.read_text(encoding="utf-8"))
                if data.get("remember_credentials", False):
                    self.username_entry.set_text(data.get("username", ""))
                    self.password_entry.set_text(data.get("password", ""))
                    self.remember_check.set_active(True)
        except Exception as error:
            print(f"Failed to load saved credentials: {error}")
        finally:
            self.loading_saved_credentials = False
            self.update_login_group_title()

    def save_credentials(self):
        if not self.remember_check or not self.remember_check.get_active():
            self.clear_saved_credentials()
            return

        DATA_DIR.mkdir(parents=True, exist_ok=True)
        data = {
            "remember_credentials": True,
            "username": self.username_entry.get_text().strip(),
            "password": self.password_entry.get_text(),
        }
        CREDENTIALS_FILE.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    def clear_saved_credentials(self):
        try:
            if CREDENTIALS_FILE.exists():
                CREDENTIALS_FILE.unlink()
        except Exception as error:
            print(f"Failed to clear saved credentials: {error}")

    def on_remember_toggled(self, button):
        if self.loading_saved_credentials:
            return

        if button.get_active():
            self.save_credentials()
        else:
            self.clear_saved_credentials()

    def refresh_server_status_async(self):
        thread = threading.Thread(target=self.fetch_server_status, daemon=True)
        thread.start()
        return True

    def fetch_server_status(self):
        try:
            payload = self.fetch_json_url(HORIZON_STATUS_URL, timeout=10)

            GLib.idle_add(self.apply_server_status, payload)

        except Exception as error:
            GLib.idle_add(self.apply_server_status_error, str(error))

    def apply_server_status(self, payload):
        try:
            players = None

            if isinstance(payload, int):
                players = payload
            elif isinstance(payload, str) and payload.isdigit():
                players = int(payload)
            elif isinstance(payload, dict):
                players = payload.get("players", payload.get("online", None))
            else:
                raise RuntimeError("Unexpected server response.")

            self.server_online = True
            self.players_online = players

            self.server_status.set_subtitle("🟢 Online")

            if players is None:
                self.players_status.set_subtitle("👥 Unknown")
            else:
                self.players_status.set_subtitle(f"👥 {int(players):,}")

            if not self.operation_in_progress:
                self.status_label.set_text("Ready")

        except Exception as error:
            self.apply_server_status_error(str(error))

        self.refresh_main_action_button()
        return False

    def apply_server_status_error(self, error_message):
        self.server_online = False
        self.players_online = None

        if self.server_status:
            self.server_status.set_subtitle("🔴 Offline / Unknown")

        if self.players_status:
            self.players_status.set_subtitle("👥 Unknown")

        if self.status_label and not self.operation_in_progress:
            self.status_label.set_text(f"Server status unavailable: {error_message}")

        self.refresh_main_action_button()
        return False

    def update_login_group_title(self):
        if not getattr(self, "login_group", None):
            return
        username = self.username_entry.get_text().strip() if self.username_entry else ""
        password = self.password_entry.get_text().strip() if self.password_entry else ""
        self.login_group.set_title("Login" if (username or password) else "Create an account on the HorizonXI Website")

    def on_credentials_changed(self, entry):
        self.update_login_group_title()
        if self.remember_check and self.remember_check.get_active() and not self.loading_saved_credentials:
            self.save_credentials()
        self.refresh_main_action_button()

    def run_install_async(self, message="Installing HorizonXI..."):
        if self.operation_in_progress:
            return

        self.game_update_check_in_progress = False
        self.game_update_check_failed = False
        self.game_update_available = False
        self.set_operation_in_progress(True)
        self.update_progress(message, 0.0)

        def progress(message, fraction=None):
            GLib.idle_add(self.update_progress, message, fraction)

        def install_worker():
            try:
                self.installer.install(progress)
                GLib.idle_add(self.on_install_finished, True, "Install complete.")
            except Exception as error:
                GLib.idle_add(self.on_install_finished, False, f"Install failed: {error}")

        threading.Thread(target=install_worker, daemon=True).start()

    def on_install_clicked(self, button):
        self.run_install_async("Repairing HorizonXI installation...")

    def on_install_finished(self, success, message):
        self.update_progress(message, 1.0 if success else 0.0)
        self.set_operation_in_progress(False)
        self.refresh_status()
        if success:
            self.refresh_game_update_status_async()
        self.refresh_addons_list()
        self.refresh_extensions_list()
        self.load_settings_ui()
        return False

    def on_main_action_clicked(self, button):
        state = self.get_main_action_state()

        if state == MAIN_ACTION_INSTALL:
            self.run_install_async("Installing HorizonXI game...")
            return

        if state == MAIN_ACTION_UPDATE:
            self.run_install_async("Updating HorizonXI game...")
            return

        if state == MAIN_ACTION_LOGIN:
            username = self.username_entry.get_text().strip()
            if not username:
                self.username_entry.grab_focus()
                self.status_label.set_text("Enter your HorizonXI username.")
            else:
                self.password_entry.grab_focus()
                self.status_label.set_text("Enter your HorizonXI password.")
            return

        if state == MAIN_ACTION_LAUNCH:
            self.launch_game_direct()
            return

    def on_nuclear_reset_clicked(self, button):
        if self.operation_in_progress:
            return

        dialog = Adw.MessageDialog(
            transient_for=self.window,
            heading="Nuclear Reset?",
            body=(
                "This will delete all HorizonXI launcher-managed runtime files: the Wine prefix, "
                "game files, official HorizonXI launcher files, managed Proton files, downloads, "
                "logs, and saved login credentials.\n\n"
                "Your Linux launcher app/project will not be deleted."
            ),
        )
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("reset", "Reset Everything")
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")
        dialog.set_response_appearance("reset", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.connect("response", self.on_nuclear_reset_response)
        dialog.present()

    def on_nuclear_reset_response(self, dialog, response):
        if response != "reset":
            return

        self.set_operation_in_progress(True)
        self.update_progress("Preparing nuclear reset...", 0.0)

        def progress(message, fraction=None):
            GLib.idle_add(self.update_progress, message, fraction)

        def reset_worker():
            try:
                self.installer.nuclear_reset(progress)
                if CREDENTIALS_FILE.exists():
                    CREDENTIALS_FILE.unlink()
                GLib.idle_add(self.on_nuclear_reset_finished, True, "Nuclear reset complete. Saved credentials deleted.")
            except Exception as error:
                GLib.idle_add(self.on_nuclear_reset_finished, False, f"Nuclear reset failed: {error}")

        threading.Thread(target=reset_worker, daemon=True).start()

    def on_nuclear_reset_finished(self, success, message):
        self.update_progress(message, 1.0 if success else 0.0)
        if success:
            self.loading_saved_credentials = True
            self.username_entry.set_text("")
            self.password_entry.set_text("")
            self.remember_check.set_active(False)
            self.loading_saved_credentials = False
        self.set_operation_in_progress(False)
        self.refresh_status()
        return False

    def on_launch_clicked(self, button):
        try:
            self.status_label.set_text("Launching official HorizonXI launcher...")
            self.launcher.launch()
            self.status_label.set_text("Official HorizonXI launcher started.")
        except Exception as error:
            self.status_label.set_text(f"Launch failed: {error}")

    def on_open_link_clicked(self, button, url):
        try:
            Gio.AppInfo.launch_default_for_uri(url, None)
            if self.status_label:
                self.status_label.set_text(f"Opened {url}")
        except Exception as error:
            if self.status_label:
                self.status_label.set_text(f"Failed to open link: {error}")

    def launch_game_direct(self):
        username = self.username_entry.get_text().strip()
        password = self.password_entry.get_text()

        if not username or not password:
            self.status_label.set_text("Enter username and password first.")
            self.refresh_main_action_button()
            return

        if self.game_update_check_in_progress:
            self.status_label.set_text("Still checking for game updates. Please wait.")
            self.refresh_main_action_button()
            return

        if self.game_update_check_failed:
            self.status_label.set_text("Game update check failed, so direct launch is blocked.")
            self.refresh_main_action_button()
            return

        if self.game_update_available:
            self.status_label.set_text("Update HorizonXI before launching.")
            self.refresh_main_action_button()
            return

        if not self.server_online:
            self.status_label.set_text("Server is offline or status is unknown.")
            self.refresh_main_action_button()
            return

        try:
            self.save_credentials()
            self.status_label.set_text("Launching HorizonXI directly...")
            self.launcher.launch_game_direct(username, password)
            self.status_label.set_text("HorizonXI game started.")
        except Exception as error:
            self.status_label.set_text(f"Direct launch failed: {error}")

    def on_backup_macros_clicked(self, button):
        try:
            backup_path = self.backup_macros()
            self.status_label.set_text(f"Macro backup created: {backup_path}")
        except Exception as error:
            self.status_label.set_text(f"Failed to backup macros: {error}")

    def backup_macros(self):
        user_dir = (
            GAME_DIR
            / "SquareEnix"
            / "FINAL FANTASY XI"
            / "USER"
        )

        if not user_dir.exists() or not user_dir.is_dir():
            raise RuntimeError("Macro USER folder not found. Launch the game at least once first.")

        documents_dir = self.get_documents_dir()
        backup_dir = documents_dir / "HorizonMacroBackup"
        backup_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%H-%M-%S_%Y-%m-%d")
        backup_file = backup_dir / f"HorizonMacroBackup_{timestamp}.zip"

        with zipfile.ZipFile(backup_file, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in user_dir.rglob("*"):
                if not path.is_file():
                    continue

                archive_name = Path("USER") / path.relative_to(user_dir)
                archive.write(path, archive_name)

        return backup_file

    def get_documents_dir(self):
        documents = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_DOCUMENTS)
        if documents:
            return Path(documents)

        return Path.home() / "Documents"

    def on_open_game_folder_clicked(self, button):
        try:
            from config import HORIZON_INSTALL_DIR

            HORIZON_INSTALL_DIR.mkdir(parents=True, exist_ok=True)

            Gio.AppInfo.launch_default_for_uri(
                HORIZON_INSTALL_DIR.as_uri(),
                None,
            )

            self.status_label.set_text("Opened HorizonXI game folder.")

        except Exception as error:
            self.status_label.set_text(f"Failed to open game folder: {error}")
