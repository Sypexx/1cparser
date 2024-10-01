import psycopg2
from ldap3 import Server, Connection, SUBTREE, MODIFY_REPLACE
import os
from dotenv import load_dotenv
import argparse
import getpass
import json
from datetime import datetime

def load_config():
    load_dotenv('settings.env')
    config = {
        'PG_HOST': os.getenv('PG_HOST'),
        'PG_DATABASE': os.getenv('PG_DATABASE'),
        'PG_USER': os.getenv('PG_USER'),
        'AD_SERVER': os.getenv('AD_SERVER'),
        'AD_USER': os.getenv('AD_USER'),
        'AD_SEARCH_BASE': os.getenv('AD_SEARCH_BASE')
    }
   
    # Запрашиваем пароли при запуске
    config['PG_PASSWORD'] = getpass.getpass("Введите пароль для PostgreSQL: ")
    config['AD_PASSWORD'] = getpass.getpass("Введите пароль для Active Directory: ")
   
    return config

class ChangeTracker:
    def __init__(self):
        self.changes = []

    def add_change(self, action, details):
        self.changes.append((action, details))

    def undo_changes(self, ad_conn):
        for action, details in reversed(self.changes):
            if action == 'create':
                print(f"Удаление созданного пользователя: {details['username']}")
                ad_conn.delete(details['dn'])
            elif action == 'update':
                print(f"Откат изменений пользователя: {details['username']}")
                ad_conn.modify(details['dn'], details['old_attributes'])
            elif action == 'delete':
                print(f"Восстановление удаленного пользователя: {details['username']}")
                ad_conn.add(details['dn'], attributes=details['attributes'])

    def clear(self):
        self.changes.clear()

    def save_to_file(self, filename):
        with open(filename, 'w') as f:
            json.dump(self.changes, f)

    @classmethod
    def load_from_file(cls, filename):
        tracker = cls()
        with open(filename, 'r') as f:
            tracker.changes = json.load(f)
        return tracker

def get_pg_users(config):
    try:
        conn = psycopg2.connect(
            host=config['PG_HOST'],
            database=config['PG_DATABASE'],
            user=config['PG_USER'],
            password=config['PG_PASSWORD']
        )
        cur = conn.cursor()
        cur.execute("SELECT username, email, full_name FROM users")
        users = cur.fetchall()
        cur.close()
        conn.close()
        return users
    except psycopg2.Error as e:
        print(f"Ошибка подключения к базе данных PostgreSQL: {e}")
        raise

def get_ad_users(conn, search_base):
    conn.search(search_base, '(objectClass=user)', SUBTREE, attributes=['sAMAccountName', 'mail', 'displayName'])
    return {entry.sAMAccountName.value: entry for entry in conn.entries}

def simulate_sync(config):
    server = Server(config['AD_SERVER'])
    conn = Connection(server, user=config['AD_USER'], password=config['AD_PASSWORD'], auto_bind=True)
   
    try:
        pg_users = get_pg_users(config)
        ad_users = get_ad_users(conn, config['AD_SEARCH_BASE'])
       
        for username, email, full_name in pg_users:
            if username in ad_users:
                changes = {}
                if email != ad_users[username].mail.value:
                    changes['mail'] = email
                if full_name != ad_users[username].displayName.value:
                    changes['displayName'] = full_name
               
                if changes:
                    print(f"Будет обновлен пользователь: {username}")
                    for attr, value in changes.items():
                        print(f"  {attr}: {ad_users[username][attr]} -> {value}")
            else:
                print(f"Будет добавлен новый пользователь: {username}")
                print(f"  email: {email}")
                print(f"  full_name: {full_name}")

        pg_usernames = set(user[0] for user in pg_users)
        for ad_username in ad_users:
            if ad_username not in pg_usernames:
                print(f"Будет удален пользователь: {ad_username}")

    finally:
        conn.unbind()

def sync_users(config):
    server = Server(config['AD_SERVER'])
    conn = Connection(server, user=config['AD_USER'], password=config['AD_PASSWORD'], auto_bind=True)
   
    tracker = ChangeTracker()

    try:
        pg_users = get_pg_users(config)
        ad_users = get_ad_users(conn, config['AD_SEARCH_BASE'])
       
        for username, email, full_name in pg_users:
            if username in ad_users:
                user_dn = ad_users[username].entry_dn
                changes = {}
                old_attributes = {}
                if email != ad_users[username].mail.value:
                    changes['mail'] = [(MODIFY_REPLACE, [email])]
                    old_attributes['mail'] = ad_users[username].mail.value
                if full_name != ad_users[username].displayName.value:
                    changes['displayName'] = [(MODIFY_REPLACE, [full_name])]
                    old_attributes['displayName'] = ad_users[username].displayName.value
               
                if changes:
                    conn.modify(user_dn, changes)
                    print(f"Обновлен пользователь: {username}")
                    tracker.add_change('update', {'username': username, 'dn': user_dn, 'old_attributes': old_attributes})
            else:
                user_dn = f"CN={full_name},{config['AD_SEARCH_BASE']}"
                attributes = {
                    'objectClass': ['top', 'person', 'organizationalPerson', 'user'],
                    'sAMAccountName': username,
                    'userPrincipalName': f"{username}@domain.com",
                    'mail': email,
                    'displayName': full_name
                }
                conn.add(user_dn, attributes=attributes)
                print(f"Добавлен новый пользователь: {username}")
                tracker.add_change('create', {'username': username, 'dn': user_dn})

        pg_usernames = set(user[0] for user in pg_users)
        for ad_username in ad_users:
            if ad_username not in pg_usernames:
                user_dn = ad_users[ad_username].entry_dn
                attributes = dict(ad_users[ad_username].entry_attributes_as_dict)
                conn.delete(user_dn)
                print(f"Удален пользователь: {ad_username}")
                tracker.add_change('delete', {'username': ad_username, 'dn': user_dn, 'attributes': attributes})

    except Exception as e:
        print(f"Произошла ошибка: {e}")
        print("Выполняется откат изменений...")
        tracker.undo_changes(conn)
    else:
        # Сохраняем изменения только если синхронизация прошла успешно
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"changes_{timestamp}.json"
        tracker.save_to_file(filename)
        print(f"Изменения сохранены в файл: {filename}")
    finally:
        conn.unbind()
        tracker.clear()

def rollback_changes(config):
    # Находим самый свежий файл с изменениями
    changes_files = [f for f in os.listdir('.') if f.startswith('changes_') and f.endswith('.json')]
    if not changes_files:
        print("Нет сохраненных изменений для отката.")
        return

    latest_file = max(changes_files)
    print(f"Загрузка изменений из файла: {latest_file}")

    tracker = ChangeTracker.load_from_file(latest_file)

    server = Server(config['AD_SERVER'])
    conn = Connection(server, user=config['AD_USER'], password=config['AD_PASSWORD'], auto_bind=True)

    try:
        tracker.undo_changes(conn)
        print("Откат изменений выполнен успешно.")
        os.remove(latest_file)
        print(f"Файл с изменениями удален: {latest_file}")
    except Exception as e:
        print(f"Ошибка при откате изменений: {e}")
    finally:
        conn.unbind()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Синхронизация пользователей между PostgreSQL и Active Directory")
    parser.add_argument("--dry-run", action="store_true", help="Выполнить пробный запуск без внесения изменений")
    parser.add_argument("--rollback", action="store_true", help="Откатить последние изменения")
    args = parser.parse_args()

    config = load_config()

    if args.dry_run:
        print("Выполняется пробный запуск...")
        simulate_sync(config)
    elif args.rollback:
        print("Выполняется откат изменений...")
        rollback_changes(config)
    else:
        try:
            sync_users(config)
            print("Синхронизация успешно завершена")
        except Exception as e:
            print(f"Произошла ошибка во время синхронизации: {e}")
            print("Изменения были отменены")
