import psycopg2
from ldap3 import Server, Connection, SUBTREE, MODIFY_REPLACE, MODIFY_ADD, MODIFY_DELETE
import os
from dotenv import load_dotenv
import argparse

# Загрузка переменных окружения
load_dotenv('settings.env')

# Параметры подключения к PostgreSQL
PG_HOST = os.getenv('PG_HOST')
PG_DATABASE = os.getenv('PG_DATABASE')
PG_USER = os.getenv('PG_USER')
PG_PASSWORD = os.getenv('PG_PASSWORD')

# Параметры подключения к Active Directory
AD_SERVER = os.getenv('AD_SERVER')
AD_USER = os.getenv('AD_USER')
AD_PASSWORD = os.getenv('AD_PASSWORD')
AD_SEARCH_BASE = os.getenv('AD_SEARCH_BASE')

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

def get_pg_users():
    try:
        conn = psycopg2.connect(host=PG_HOST, database=PG_DATABASE, user=PG_USER, password=PG_PASSWORD)
        cur = conn.cursor()
        cur.execute("SELECT username, email, full_name FROM users")
        users = cur.fetchall()
        cur.close()
        conn.close()
        return users
    except psycopg2.Error as e:
        print(f"Ошибка при подключении к Postgresql: {e}")
        raise

def get_ad_users(conn):
    conn.search(AD_SEARCH_BASE, '(objectClass=user)', SUBTREE, attributes=['sAMAccountName', 'mail', 'displayName'])
    return {entry.sAMAccountName.value: entry for entry in conn.entries}

def sync_users():
    # Подключение к Active Directory
    server = Server(AD_SERVER)
    conn = Connection(server, user=AD_USER, password=AD_PASSWORD, auto_bind=True)

    # Инициализация ChangeTracker
    tracker = ChangeTracker()

    try:
        # Получение пользователей из PostgreSQL и Active Directory
        pg_users = get_pg_users()
        ad_users = get_ad_users(conn)

        for username, email, full_name in pg_users:
            if username in ad_users:
                # Обновление существующего пользователя
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
                    print(f"Обновленный пользователь: {username}")
                    tracker.add_change('update', {'username': username, 'dn': user_dn, 'old_attributes': old_attributes})
            else:
                # Создание нового пользователя
                user_dn = f"CN={full_name},{AD_SEARCH_BASE}"
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

        # Удаление пользователей из AD, которых нет в PostgreSQL
        pg_usernames = set(user[0] for user in pg_users)
        for ad_username in ad_users:
            if ad_username not in pg_usernames:
                user_dn = ad_users[ad_username].entry_dn
                attributes = dict(ad_users[ad_username].entry_attributes_as_dict)
                conn.delete(user_dn)
                print(f"Удаленный пользователь: {ad_username}")
                tracker.add_change('delete', {'username': ad_username, 'dn': user_dn, 'attributes': attributes})

    except Exception as e:
        print(f"Ошибка: {e}")
        print("Восстановление изменений...")
        tracker.undo_changes(conn)
    finally:
        conn.unbind()
        tracker.clear()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Синхронизация между postgresql и ActiveDirectory")
    parser.add_argument("--dry-run", action="store_true", help="Холостой запуск без приминения изменений")
    args = parser.parse_args()

    if args.dry_run:
        print("Холостой запуск...")
        # Implement dry run logic here
    else:
        try:
            sync_users()
            print("Синхронизация прошла успешно")
        except Exception as e:
            print(f"Ошибка во время синхронизации {e}")
            print("Изменения были отменены")
