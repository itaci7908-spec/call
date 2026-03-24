import os
import json
import threading
from datetime import datetime, timedelta

# Базовые настройки Kivy
from kivy.config import Config
Config.set('graphics', 'resizable', '0')

from kivy.lang import Builder
from kivy.uix.screenmanager import ScreenManager, Screen, NoTransition
from kivy.properties import NumericProperty, StringProperty, BooleanProperty
from kivy.clock import Clock
from kivy.utils import platform

# KivyMD компоненты
from kivymd.app import MDApp
from kivymd.uix.button import MDRaisedButton, MDFloatingActionButton, MDFlatButton
from kivymd.uix.dialog import MDDialog
from kivymd.uix.spinner import MDSpinner
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.textfield import MDTextField
from kivymd.uix.filemanager import MDFileManager

# ИИ и Работа с изображениями
import google.generativeai as genai
from PIL import Image

# --- КОНФИГУРАЦИЯ ИИ ---
GOOGLE_API_KEY = "AIzaSyDyS7Ay80zfVoWwIUNs9idT5tGWp1cuJVQ" # Твой ключ
os.environ["GOOGLE_API_USE_MTLS"] = "never"
genai.configure(api_key=GOOGLE_API_KEY, transport='rest')

class StepScreen(Screen):
    question_text = StringProperty("")
    is_gender_screen = BooleanProperty(False)
    selected_gender = StringProperty("male")
    step_key = StringProperty("")

    def select_gender(self, gender):
        self.selected_gender = gender

    def next_step(self):
        app = MDApp.get_running_app()
        if self.is_gender_screen:
            app.user_data["gender"] = self.selected_gender
        else:
            val = self.ids.input_field.text
            if not val: return
            try:
                app.user_data[self.step_key] = float(val)
            except ValueError:
                return

        idx = app.steps.index(self.step_key)
        if idx < len(app.steps) - 1:
            self.manager.current = app.steps[idx + 1]
        else:
            app.user_data["last_weight_date"] = datetime.now().strftime("%Y-%m-%d")
            app.final_calculate()

class DashboardScreen(Screen):
    dialog = None
    loading_spinner = None

    def __init__(self, **kw):
        super().__init__(**kw)
        # Менеджер файлов вместо проводника Windows
        self.file_manager = MDFileManager(
            exit_manager=self.exit_manager,
            select_path=self.select_path
        )

    def on_enter(self):
        app = MDApp.get_running_app()
        app.update_history_ui()
        Clock.schedule_once(lambda dt: app.check_weekly_weight(), 1)

    def open_camera(self):
        # Определяем начальный путь для выбора фото
        if platform == 'android':
            path = "/sdcard"
        else:
            path = os.path.expanduser("~")
        self.file_manager.show(path)

    def select_path(self, path):
        self.exit_manager()
        if path and os.path.isfile(path):
            self.show_loading()
            threading.Thread(target=self.bg_analyze, args=(path,)).start()

    def exit_manager(self, *args):
        self.file_manager.close()

    def bg_analyze(self, path):
        import base64
        import requests
        
        try:
            with open(path, "rb") as image_file:
                encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
            
            # Прямой запрос к API без тяжелых библиотек
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GOOGLE_API_KEY}"
            payload = {
                "contents": [{
                    "parts": [
                        {"text": "Название | Калории (только текст, формат: Название | Число)"},
                        {"inline_data": {"mime_type": "image/jpeg", "data": encoded_string}}
                    ]
                }]
            }
            
            response = requests.post(url, json=payload, timeout=30)
            data = response.json()
            
            if "candidates" in data:
                res_text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                if "|" in res_text:
                    name, kcal = res_text.split("|")
                    Clock.schedule_once(lambda dt: self.show_confirm(name.strip(), kcal.strip()))
                    return

            Clock.schedule_once(lambda dt: self.hide_loading())
        except Exception as e:
            print(f"Ошибка запроса: {e}")
            Clock.schedule_once(lambda dt: self.hide_loading())

    def show_confirm(self, name, kcal):
        self.hide_loading()
        self.dialog = MDDialog(
            title="AIEat нашел еду", 
            text=f"Это {name} ({kcal} ккал)?",
            buttons=[
                MDFlatButton(text="НЕТ", on_release=lambda x: self.dialog.dismiss()),
                MDRaisedButton(text="ДА", on_release=lambda x: self.confirm_selection(name, kcal))
            ]
        )
        self.dialog.open()

    def confirm_selection(self, name, kcal):
        app = MDApp.get_running_app()
        try:
            clean_kcal = ''.join(filter(str.isdigit, str(kcal)))
            val = int(clean_kcal) if clean_kcal else 0
            app.calories_left -= val
            
            if "history" not in app.user_data or not isinstance(app.user_data["history"], list):
                app.user_data["history"] = []
            
            app.user_data["history"].append({
                "name": str(name), "kcal": val, "t": datetime.now().strftime("%H:%M")
            })
            app.save_progress()
            app.update_history_ui()
        except: pass
        self.dialog.dismiss()

    def show_loading(self):
        if not self.loading_spinner:
            self.loading_spinner = MDDialog(
                title="Анализ фото...", type="custom",
                content_cls=MDSpinner(size_hint=(None, None), size=("40dp", "40dp"), pos_hint={'center_x': .5}),
                auto_dismiss=False
            )
        self.loading_spinner.open()

    def hide_loading(self):
        if self.loading_spinner: self.loading_spinner.dismiss()

KV = '''
<StepScreen>:
    md_bg_color: [1, 1, 1, 1]
    MDBoxLayout:
        orientation: 'vertical'
        padding: dp(25)
        spacing: dp(30)
        MDLabel:
            text: "AIEat"
            font_style: "H5"
            halign: "center"
            theme_text_color: "Primary"
        MDLabel:
            text: root.question_text
            font_style: "H4"
            halign: "center"
        MDBoxLayout:
            orientation: 'vertical'
            adaptive_height: True
            spacing: dp(20)
            MDTextField:
                id: input_field
                hint_text: "Введите число"
                mode: "fill"
                opacity: 0 if root.is_gender_screen else 1
            MDBoxLayout:
                adaptive_height: True
                spacing: dp(15)
                pos_hint: {"center_x": .5}
                opacity: 1 if root.is_gender_screen else 0
                MDRaisedButton:
                    text: "МУЖЧИНА"
                    md_bg_color: [0, 0.7, 0.6, 1] if root.selected_gender == "male" else [0.9, 0.9, 0.9, 1]
                    on_release: root.select_gender("male")
                MDRaisedButton:
                    text: "ЖЕНЩИНА"
                    md_bg_color: [0, 0.7, 0.6, 1] if root.selected_gender == "female" else [0.9, 0.9, 0.9, 1]
                    on_release: root.select_gender("female")
        Widget:
        MDRaisedButton:
            text: "ПРОДОЛЖИТЬ"
            size_hint_x: 1
            height: dp(50)
            on_release: root.next_step()

<DashboardScreen>:
    md_bg_color: [0.96, 0.96, 0.96, 1]
    MDFloatLayout:
        MDBoxLayout:
            orientation: 'vertical'
            padding: dp(15)
            spacing: dp(15)
            pos_hint: {"top": 1}
            MDBoxLayout:
                adaptive_height: True
                MDLabel:
                    text: "Мой день"
                    font_style: "H5"
                MDIconButton:
                    icon: "cog"
                    on_release: app.open_settings()
            MDCard:
                size_hint: 1, None
                height: dp(120)
                radius: [20,]
                md_bg_color: [1, 1, 1, 1]
                MDLabel:
                    text: f"{app.calories_left}\\nккал осталось"
                    halign: "center"
                    font_style: "H4"
                    theme_text_color: "Custom"
                    text_color: [0.9, 0.1, 0.1, 1] if app.calories_left < 0 else [0, 0, 0, 1]
            MDLabel:
                text: "СЕГОДНЯШНЯЯ ЕДА"
                font_style: "Caption"
                theme_text_color: "Hint"
            MDCard:
                size_hint: 1, None
                height: dp(300)
                radius: [20,]
                padding: dp(15)
                md_bg_color: [1, 1, 1, 1]
                MDLabel:
                    text: app.history_text
                    halign: "left"
                    valign: "top"
                    text_size: self.width - dp(30), None
        MDFloatingActionButton:
            icon: "camera"
            pos_hint: {"center_x": .5, "y": .04}
            md_bg_color: [0, 0.7, 0.6, 1]
            on_release: root.open_camera()
'''

class AIEatApp(MDApp):
    calories_left = NumericProperty(0)
    history_text = StringProperty("Список пуст")
    user_data = {}
    steps = ["gender", "age", "height", "weight", "target_weight", "months"]

    def build(self):
        self.theme_cls.theme_style = "Light"
        self.theme_cls.primary_palette = "Teal"
        Builder.load_string(KV)
        sm = ScreenManager(transition=NoTransition())
        
        q = {"gender":"Пол","age":"Возраст","height":"Рост","weight":"Вес","target_weight":"Цель","months":"Срок"}
        for s in self.steps:
            sm.add_widget(StepScreen(name=s, question_text=q[s], is_gender_screen=(s=="gender"), step_key=s))
        sm.add_widget(DashboardScreen(name="dashboard"))
        
        data_path = self.get_data_path()
        if os.path.exists(data_path):
            try:
                with open(data_path, "r") as f:
                    self.user_data = json.load(f)
                    self.calories_left = self.user_data.get("calories", 0)
                    self.theme_cls.theme_style = self.user_data.get("theme", "Light")
                    sm.current = "dashboard"
            except: pass
        return sm

    def get_data_path(self):
        # На Android сохраняем в системную папку приложения
        if platform == 'android':
            return os.path.join(self.user_data_dir, "user_data.json")
        return "user_data.json"

    def update_history_ui(self):
        h = self.user_data.get("history", [])
        items = h[-10:] # Только последние 10 записей
        lines = [f"• [{i.get('t','--:--')}] {i.get('name','?')} — {i.get('kcal',0)} ккал" for i in items]
        self.history_text = "\n".join(lines) if lines else "Пока ничего не съедено"

    def final_calculate(self):
        d = self.user_data
        g, w, h, a = d.get("gender", "male"), d.get("weight", 70), d.get("height", 170), d.get("age", 25)
        tw, m = d.get("target_weight", 65), d.get("months", 3)
        
        mod = 5 if g == "male" else -161
        bmr = (10 * w) + (6.25 * h) - (5 * a) + mod
        deficit = ((w - tw) * 7700) / (m * 30.4)
        self.calories_left = int(max(1200, bmr * 1.2 - deficit))
        self.save_progress()
        self.root.current = "dashboard"

    def open_settings(self):
        box = MDBoxLayout(orientation='vertical', spacing="10dp", adaptive_height=True, padding="10dp")
        self.set_kcal = MDTextField(text=str(self.calories_left), hint_text="Калории")
        theme_btn = MDRaisedButton(text=f"ТЕМА", size_hint_x=1, on_release=self.toggle_theme)
        box.add_widget(self.set_kcal); box.add_widget(theme_btn)
        self.set_dialog = MDDialog(title="Настройки", type="custom", content_cls=box,
            buttons=[MDFlatButton(text="ОК", on_release=self.save_settings)])
        self.set_dialog.open()

    def toggle_theme(self, btn):
        self.theme_cls.theme_style = "Dark" if self.theme_cls.theme_style == "Light" else "Light"
        self.user_data["theme"] = self.theme_cls.theme_style
        self.save_progress()

    def save_settings(self, *args):
        try: self.calories_left = int(float(self.set_kcal.text))
        except: pass
        self.save_progress(); self.set_dialog.dismiss()

    def save_progress(self):
        self.user_data["calories"] = self.calories_left
        with open(self.get_data_path(), "w") as f:
            json.dump(self.user_data, f)

    def check_weekly_weight(self):
        last = self.user_data.get("last_weight_date", "2000-01-01")
        if datetime.now() - datetime.strptime(last, "%Y-%m-%d") >= timedelta(days=7):
            f = MDTextField(hint_text="Вес сегодня"); d = MDDialog(title="Взвесимся?", type="custom", content_cls=f,
                buttons=[MDRaisedButton(text="OK", on_release=lambda x: self.update_weight(f.text, d))])
            d.open()

    def update_weight(self, v, d):
        if v:
            self.user_data["weight"] = float(v)
            self.user_data["last_weight_date"] = datetime.now().strftime("%Y-%m-%d")
            self.final_calculate()
        d.dismiss()

if __name__ == "__main__":
    AIEatApp().run()