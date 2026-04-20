# website/app.py

from flask import Flask, render_template, request, redirect, url_for, flash, abort
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
import os
import json
import sqlite3
from datetime import datetime, timezone, timedelta
import re

app = Flask(__name__)
app.secret_key = 'REPLACE_WITH_A_VERY_SECRET_KEY'

USERS_DB = {
    "admin":  {"password": "admin", "role": "admin"},
    "scout":  {"password": "123",   "role": "editor"},
    "rl":     {"password": "123",   "role": "party_manager"}
}

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

class User(UserMixin):
    def __init__(self, id, role):
        self.id = id
        self.role = role
    
    @property
    def is_admin(self):
        return self.role == 'admin'
    
    @property
    def can_edit_objects(self):
        return self.role in ['admin', 'editor']
    
    @property
    def can_manage_party(self):
        return self.role in ['admin', 'party_manager']

@login_manager.user_loader
def load_user(user_id):
    if user_id not in USERS_DB:
        return None
    return User(user_id, USERS_DB[user_id]['role'])

# --- ПУТИ К ФАЙЛАМ ---
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "bot_data")
SIGNALS_DIR = os.path.join(BASE_DIR, "bot_signals")
DB_PATH = os.path.join(DATA_DIR, "game_bot.db")

LOCATIONS_FILE = os.path.join(BASE_DIR, "locations.txt")
OBJECT_NAMES_FILE = os.path.join(BASE_DIR, "object_names.txt")
SERVER_NAMES_FILE = os.path.join(BASE_DIR, "server_names.json")
ABBREVIATIONS_FILE = os.path.join(BASE_DIR, "abbreviations.json")
ICONS_FILE = os.path.join(BASE_DIR, "icons.json")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(SIGNALS_DIR, exist_ok=True)


def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def read_text_file(filepath, default_content=''):
    try:
        with open(filepath, 'r', encoding='utf-8') as f: return f.read()
    except: return default_content

def write_text_file(filepath, content):
    cleaned = "\n".join(line.strip() for line in content.splitlines() if line.strip())
    with open(filepath, 'w', encoding='utf-8') as f: f.write(cleaned)

def get_server_name_mapping():
    try:
        with open(SERVER_NAMES_FILE, 'r', encoding='utf-8') as f: return json.load(f)
    except: return {}

def get_role_names_mapping(guild_id):
    try:
        path = os.path.join(DATA_DIR, f"roles_{guild_id}.json")
        with open(path, 'r', encoding='utf-8') as f: return json.load(f)
    except: return {}

def send_update_signal(guild_id):
    try:
        with open(os.path.join(SIGNALS_DIR, f"update_signal_{guild_id}.txt"), 'w') as f:
            f.write(str(datetime.utcnow()))
    except: pass


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
        
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        if username in USERS_DB and USERS_DB[username]['password'] == password:
            user = User(username, USERS_DB[username]['role'])
            login_user(user)
            return redirect(url_for('index'))
        
        flash('Неверный логин или пароль', 'danger')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))


@app.route('/')
@login_required
def index():
    server_names = get_server_name_mapping()
    configs = []
    for guild_id, guild_name in server_names.items():
        if os.path.exists(os.path.join(DATA_DIR, f"data_{guild_id}.json")):
             configs.append({'id': guild_id, 'name': guild_name})
    return render_template('index.html', servers=sorted(configs, key=lambda x: x['name']))

@app.route('/stats')
@login_required
def stats_page():
    if not current_user.is_admin:
        flash('Доступ к статистике только у Администратора.', 'warning')
        return redirect(url_for('index'))

    conn = get_db_connection()
    try:
        users = conn.execute('SELECT username, added_count, guild_id FROM user_stats ORDER BY added_count DESC LIMIT 50').fetchall()
    except:
        users = []
    conn.close()
    
    server_names = get_server_name_mapping()
    stats_data = []
    for u in users:
        g_name = server_names.get(str(u['guild_id']), str(u['guild_id']))
        stats_data.append({'username': u['username'], 'count': u['added_count'], 'guild': g_name})

    return render_template('stats.html', stats=stats_data)

@app.route('/lists', methods=['GET', 'POST'])
@login_required
def edit_lists():
    if not current_user.is_admin:
        flash('Глобальные настройки доступны только Администратору.', 'warning')
        return redirect(url_for('index'))

    if request.method == 'POST':
        if 'locations' in request.form: write_text_file(LOCATIONS_FILE, request.form['locations'])
        if 'object_names' in request.form: write_text_file(OBJECT_NAMES_FILE, request.form['object_names'])
        try:
            if 'abbreviations' in request.form:
                json.loads(request.form['abbreviations'])
                with open(ABBREVIATIONS_FILE, 'w', encoding='utf-8') as f: f.write(request.form['abbreviations'])
            if 'icons' in request.form:
                json.loads(request.form['icons'])
                with open(ICONS_FILE, 'w', encoding='utf-8') as f: f.write(request.form['icons'])
            flash('Глобальные настройки сохранены!', 'success')
        except json.JSONDecodeError:
            flash('Ошибка в синтаксисе JSON', 'danger')
        return redirect(url_for('edit_lists'))
    
    return render_template('edit_lists.html', 
                           locations=read_text_file(LOCATIONS_FILE), 
                           object_names=read_text_file(OBJECT_NAMES_FILE),
                           abbreviations=read_text_file(ABBREVIATIONS_FILE, '{}'),
                           icons=read_text_file(ICONS_FILE, '{}'))

@app.route('/server/<guild_id>', methods=['GET', 'POST'])
@login_required
def edit_server(guild_id):
    filepath = os.path.join(DATA_DIR, f"data_{guild_id}.json")
    if not os.path.exists(filepath):
        flash('Сервер не найден.', 'danger')
        return redirect(url_for('index'))

    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    if request.method == 'POST':
        if current_user.can_edit_objects and 'allowed_roles' in request.form:
            roles_str = request.form.get('allowed_roles', '')
            role_ids = [int(r.strip()) for r in roles_str.replace(',', '\n').split() if r.strip().isdigit()]
            data['allowed_roles'] = role_ids
            flash('Роли для объектов обновлены.', 'success')

        if current_user.can_manage_party and 'party_admin_roles' in request.form:
            p_roles_str = request.form.get('party_admin_roles', '')
            p_role_ids = [int(r.strip()) for r in p_roles_str.replace(',', '\n').split() if r.strip().isdigit()]
            data['party_admin_roles'] = p_role_ids
            flash('Роли для Пати Мейкера обновлены.', 'success')

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4)
        
        return redirect(url_for('edit_server', guild_id=guild_id))

    active_items = sorted(data.get('items', []), key=lambda x: x.get('time', 0))
    server_names = get_server_name_mapping()
    role_names_map = get_role_names_mapping(guild_id)

    def format_roles(id_list):
        result = []
        for rid in id_list:
            name = role_names_map.get(str(rid), "Неизвестная роль")
            result.append(f"{rid} # {name}")
        return "\n".join(result)

    allowed_roles_text = format_roles(data.get('allowed_roles', []))
    party_roles_text = format_roles(data.get('party_admin_roles', []))

    return render_template('edit_server.html', 
                           guild_id=guild_id, 
                           guild_name=server_names.get(guild_id, guild_id),
                           allowed_roles=allowed_roles_text,
                           party_admin_roles=party_roles_text,
                           items=active_items,
                           now_timestamp=int(datetime.now(timezone.utc).timestamp()))

@app.route('/server/<guild_id>/edit/<int:item_index>', methods=['POST'])
@login_required
def edit_item(guild_id, item_index):
    if not current_user.can_edit_objects:
        flash('У вас нет прав редактировать объекты.', 'danger')
        return redirect(url_for('edit_server', guild_id=guild_id))

    filepath = os.path.join(DATA_DIR, f"data_{guild_id}.json")
    new_name = request.form.get('new_name', '').strip()
    new_location = request.form.get('new_location', '').strip()
    new_time_str = request.form.get('new_time', '').strip()

    try:
        with open(filepath, 'r+', encoding='utf-8') as f:
            data = json.load(f)
            items = sorted(data.get('items', []), key=lambda x: x.get('time', 0))

            if 0 <= item_index < len(items):
                target_item_snapshot = items[item_index]
                real_item = None
                for it in data['items']:
                    if it == target_item_snapshot:
                        real_item = it
                        break
                
                if real_item:
                    if new_name: real_item['object_name'] = new_name
                    if new_location: real_item['location'] = new_location
                    if new_time_str:
                        hours, minutes = 0, 0
                        processed = new_time_str.lower().replace(' ', '')
                        if 'ч' in processed or 'h' in processed or 'м' in processed or 'm' in processed:
                            h_match = re.search(r'(\d+)[чh]', processed)
                            if h_match: hours = int(h_match.group(1))
                            m_match = re.search(r'(\d+)[мm]', processed)
                            if m_match: minutes = int(m_match.group(1))
                        elif ':' in processed:
                            parts = processed.split(':')
                            hours, minutes = int(parts[0]), int(parts[1])
                        elif processed.isdigit():
                            minutes = int(processed)
                        
                        if hours == 0 and minutes == 0: raise ValueError
                        new_exp = datetime.now(timezone.utc) + timedelta(hours=hours, minutes=minutes)
                        real_item['time'] = int(new_exp.timestamp())

                    f.seek(0)
                    json.dump(data, f, indent=4)
                    f.truncate()
                    send_update_signal(guild_id)
                    flash('Объект обновлен!', 'success')
                else:
                    flash('Объект не найден.', 'warning')
    except Exception as e:
        flash(f'Ошибка: {e}', 'danger')

    return redirect(url_for('edit_server', guild_id=guild_id))

@app.route('/server/<guild_id>/delete/<int:item_index>', methods=['POST'])
@login_required
def delete_item(guild_id, item_index):
    if not current_user.can_edit_objects:
        flash('У вас нет прав удалять объекты.', 'danger')
        return redirect(url_for('edit_server', guild_id=guild_id))

    filepath = os.path.join(DATA_DIR, f"data_{guild_id}.json")
    try:
        with open(filepath, 'r+', encoding='utf-8') as f:
            data = json.load(f)
            sorted_items = sorted(data.get('items', []), key=lambda x: x.get('time', 0))
            if 0 <= item_index < len(sorted_items):
                item_to_remove = sorted_items[item_index]
                data['items'].remove(item_to_remove)
                f.seek(0)
                json.dump(data, f, indent=4)
                f.truncate()
                send_update_signal(guild_id)
                flash('Объект удален.', 'success')
    except Exception as e:
        flash(f'Ошибка: {e}', 'danger')
        
    return redirect(url_for('edit_server', guild_id=guild_id))

@app.route('/party_maker')
@login_required
def party_maker():
    if not current_user.can_manage_party:
        flash('Доступ к Пати Мейкеру запрещен.', 'warning')
        return redirect(url_for('index'))

    if not os.path.exists(DB_PATH):
        flash('База данных бота еще не создана.', 'warning')
        return render_template('party_maker.html', setups=[])

    conn = get_db_connection()
    try: setups = conn.execute('SELECT * FROM setups').fetchall()
    except: setups = []
    conn.close()
    return render_template('party_maker.html', setups=setups)

@app.route('/party_maker/create', methods=['POST'])
@login_required
def create_setup():
    if not current_user.can_manage_party: return redirect(url_for('index'))

    name = request.form.get('setup_name')
    party_count = int(request.form.get('party_count'))
    
    parties_data = []
    for i in range(1, party_count + 1):
        roles_text = request.form.get(f'roles_{i}', '').strip()
        processed_lines = []
        for idx, line in enumerate(roles_text.split('\n'), 1):
            clean = line.strip()
            if not clean: continue
            if not re.match(r'^\d+[\.\)]', clean):
                processed_lines.append(f"{idx}. {clean}")
            else:
                processed_lines.append(clean)
        final_text = "\n".join(processed_lines)
        parties_data.append((i, final_text))

    conn = get_db_connection()
    try:
        exists = conn.execute('SELECT name FROM setups WHERE name = ?', (name,)).fetchone()
        if exists:
            flash(f'Сетап "{name}" уже существует!', 'danger')
        else:
            conn.execute('INSERT INTO setups (name, party_count) VALUES (?, ?)', (name, party_count))
            for p_num, p_text in parties_data:
                conn.execute('INSERT INTO setup_parties (setup_name, party_number, roles_text) VALUES (?, ?, ?)', (name, p_num, p_text))
            conn.commit()
            flash(f'Сетап "{name}" создан!', 'success')
    except Exception as e:
        flash(f'Ошибка БД: {e}', 'danger')
    finally:
        conn.close()
    return redirect(url_for('party_maker'))

@app.route('/party_maker/delete/<name>', methods=['POST'])
@login_required
def delete_setup(name):
    if not current_user.can_manage_party: return redirect(url_for('index'))

    conn = get_db_connection()
    try:
        conn.execute('DELETE FROM setup_parties WHERE setup_name = ?', (name,))
        conn.execute('DELETE FROM setups WHERE name = ?', (name,))
        conn.commit()
        flash(f'Сетап "{name}" удален.', 'success')
    except Exception as e:
        flash(f'Ошибка удаления: {e}', 'danger')
    finally:
        conn.close()
    return redirect(url_for('party_maker'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)