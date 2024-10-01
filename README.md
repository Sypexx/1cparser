# Скрипт синхронизации пользователей из PostgreSQL в Active Directory

Этот скрипт синхронизирует пользователей из базы данных PostgreSQL в Active Directory. Он поддерживает добавление, обновление и удаление пользователей в Active Directory на основе данных из PostgreSQL, а также предоставляет возможность пробного запуска и отката изменений.

## Требования

- Python 3.8 или выше
- PostgreSQL (только для чтения)
- Доступ к Active Directory (с правами на изменение)
- Права на создание и удаление файлов в директории скрипта

## Установка

1. Клонируйте репозиторий: git clone [https://github.com/Sypexx/1cparser.git] cd 1cparser
2. Создайте виртуальное окружение и активируйте его: python -m venv venv source venv/bin/activate
3. Установите необходимые зависимости: pip install psycopg2-binary ldap3 python-dotenv
4. Создайте файл `settings.env` в корневой директории проекта со следующим содержимым:
PG_HOST=localhost
PG_DATABASE=your_database_name
PG_USER=your_username
AD_SERVER=your_ad_server
AD_USER=your_ad_username
AD_SEARCH_BASE=DC=your,DC=domain,DC=com

Замените значения на соответствующие вашей конфигурации.

## Использование

Скрипт поддерживает три режима работы:

1. Обычная синхронизация: python sync_users.py
2. Пробный запуск (без внесения изменений в Active Directory): python sync_users.py --dry-run
3. Откат последних изменений в Active Directory: python sync_users.py --rollback

При запуске скрипт запросит пароли для PostgreSQL и Active Directory.

## Функциональность

- Чтение данных пользователей из PostgreSQL
- Синхронизация пользователей из PostgreSQL в Active Directory:
- Добавление новых пользователей в Active Directory
- Обновление существующих пользователей в Active Directory
- Удаление пользователей из Active Directory, которых нет в PostgreSQL
- Пробный запуск для просмотра планируемых изменений в Active Directory
- Откат последних внесенных изменений в Active Directory

## Структура базы данных PostgreSQL

Скрипт ожидает наличия таблицы `users` в PostgreSQL со следующей структурой:

```sql
CREATE TABLE users (
 id SERIAL PRIMARY KEY,
 username VARCHAR(50) UNIQUE NOT NULL,
 email VARCHAR(100) UNIQUE NOT NULL,
 full_name VARCHAR(100) NOT NULL
);

Важно: скрипт только читает данные из этой таблицы и не вносит в неё изменения.

Безопасность
Пароли запрашиваются при каждом запуске скрипта и не сохраняются в файлах
Файл settings.env должен быть защищен от несанкционированного доступа
Рекомендуется использовать учетную запись с правами только на чтение для доступа к PostgreSQL
Для Active Directory требуется учетная запись с правами на изменение пользователей
Логирование и отслеживание изменений
Скрипт создает JSON-файлы с записями об изменениях в Active Directory после каждой успешной синхронизации
Эти файлы используются для отката изменений при необходимости
Устранение неполадок
Если вы столкнулись с проблемами:

Убедитесь, что все зависимости установлены корректно
Проверьте правильность данных в файле settings.env
Убедитесь, что у вас есть необходимые права доступа к PostgreSQL (чтение) и Active Directory (изменение)
Проверьте сетевое подключение к серверам PostgreSQL и Active Directory
