# Підключення Gmail для кодів FinSight

Коди надсилає одна скринька відправника FinSight через Gmail API. Користувачі
FinSight не повинні входити через Google. Доступ потрібен лише gmail.send.

## Одноразове налаштування

1. Створіть проєкт у https://console.cloud.google.com/ і ввімкніть Gmail API.
2. У Google Auth Platform налаштуйте Branding/Audience. Для локального тестування
   оберіть External / Testing і додайте скриньку відправника до Test users.
3. У Data Access додайте https://www.googleapis.com/auth/gmail.send.
4. Створіть OAuth client типу Desktop app, завантажте JSON і збережіть локально як
   E:\FinSight\secrets\gmail_client_secret.json. Не надсилайте його в чат.
5. Із кореня репозиторію запустіть:

   .\.venv\Scripts\python.exe backend/gmail_authorize.py --client-secret secrets/gmail_client_secret.json

   У браузері самостійно увійдіть у скриньку відправника та надайте доступ.
   Помічник запише secrets/gmail_token.json, не виводячи токени. Для повторного
   підключення використовуйте --replace. Наявний token без цього не перезаписується.
6. Відкрийте E:\FinSight\.env.gmail і впишіть email після знака =:

   GMAIL_SENDER=ваша_адреса@gmail.com

   Це має бути та сама скринька, якій ви надали OAuth-доступ.
   Compose автоматично читає файл для API; додатковий --env-file не потрібен.
   Файл ігнорується Git. Якщо його немає, створіть .env.gmail із рядком GMAIL_SENDER=.
   GMAIL_TOKEN_PATH залишається в .env.docker, за замовчуванням —
   ./secrets/gmail_token.json. Чинні паролі БД та ключі Flask/JWT не змінюйте.

Файли secrets/ ігноруються Git. Вони поза build context бекенду, а token
монтується read-only лише в API-контейнер. Runtime оновлює Google access token
в оперативній пам’яті; початковий файл не потрібно змінювати при кожному листі.

## Активація

До підключення скриньки робочий Compose не оновлюємо. Спочатку підготуйте OAuth,
після цього виконайте production-збірку, міграцію та перевірку реального листа.
Без Gmail вхід через OTP повертає помилку доставки й не видає access token.

У режимі Google OAuth Testing refresh token для Gmail може діяти лише 7 днів.
Для постійної роботи налаштуйте Publishing status відповідно до вимог Google;
зміна пароля чи відкликання доступу також може вимагати повторного OAuth.
Це окремий строк від 7-денної авторизації та 90-денної довіри FinSight.

Документація:
- https://developers.google.com/workspace/gmail/api/guides/sending
- https://developers.google.com/workspace/gmail/api/auth/scopes
- https://developers.google.com/identity/protocols/oauth2#expiration
