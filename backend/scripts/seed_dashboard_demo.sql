-- User-requested dashboard fixtures. Additive and safe to run repeatedly.
BEGIN;
DO $$
DECLARE
    owner_id integer;
    demo_account integer;
    month_start timestamptz;
    month_index integer;
BEGIN
    SELECT id INTO STRICT owner_id FROM public."user"
    WHERE lower(email) = 'pavlohorokh4@gmail.com' FOR UPDATE;

    SELECT id INTO demo_account FROM account
    WHERE user_id = owner_id AND name = '[Демо] Рахунок для перевірки кабінету' AND currency = 'UAH';
    IF demo_account IS NULL THEN
        INSERT INTO account (user_id, name, account_type, currency, balance, created_at, created_by)
        VALUES (owner_id, '[Демо] Рахунок для перевірки кабінету', 'bank', 'UAH', 0,
                date_trunc('month', now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC' - interval '6 months', now())
        RETURNING id INTO demo_account;
    END IF;

    INSERT INTO category (name) VALUES
        ('Продукти'), ('Житло'), ('Транспорт'), ('Комунальні послуги'),
        ('Дозвілля'), ('Здоров’я'), ('Підписки')
    ON CONFLICT (name) DO NOTHING;

    FOR month_index IN 0..6 LOOP
        month_start := (date_trunc('month', now() AT TIME ZONE 'UTC') - (6 - month_index) * interval '1 month') AT TIME ZONE 'UTC';
        INSERT INTO "transaction" (account_id, amount, transaction_type, description, category_id, created_at)
        SELECT demo_account, fixture.amount, fixture.kind, fixture.description, category.id,
               month_start + fixture.day * interval '1 day' + interval '10 hours'
        FROM (VALUES
            (42000 + month_index * 1500, 'income', '[Демо] Зарплата', NULL, 4),
            (4500 + month_index * 400, 'income', '[Демо] Фриланс', NULL, 14),
            (9000, 'expense', '[Демо] Оренда житла', 'Житло', 5),
            (6500 + month_index * 180, 'expense', '[Демо] Продукти за місяць', 'Продукти', 11),
            (1700 + month_index * 80, 'expense', '[Демо] Транспорт', 'Транспорт', 8),
            (1800 + month_index * 50, 'expense', '[Демо] Комунальні послуги', 'Комунальні послуги', 9),
            (1400 + month_index * 100, 'expense', '[Демо] Дозвілля', 'Дозвілля', 15),
            (950 + month_index * 50, 'expense', '[Демо] Здоров’я', 'Здоров’я', 16),
            (299, 'expense', '[Демо] Netflix', 'Підписки', 6),
            (199, 'expense', '[Демо] Spotify', 'Підписки', 7),
            (39, 'expense', '[Демо] iCloud', 'Підписки', 10)
        ) AS fixture(amount, kind, description, category_name, day)
        LEFT JOIN category ON category.name = fixture.category_name
        WHERE NOT EXISTS (
            SELECT 1 FROM "transaction" existing
            WHERE existing.account_id = demo_account
              AND existing.description = fixture.description
              AND existing.created_at >= month_start
              AND existing.created_at < month_start + interval '1 month'
        );
    END LOOP;

    INSERT INTO subscription (user_id, name, amount, currency, billing_day)
    SELECT owner_id, fixture.name, fixture.amount, 'UAH', fixture.day
    FROM (VALUES ('[Демо] Netflix', 299, 7), ('[Демо] Spotify', 199, 8), ('[Демо] iCloud', 39, 11))
        AS fixture(name, amount, day)
    WHERE NOT EXISTS (SELECT 1 FROM subscription existing
        WHERE existing.user_id = owner_id AND existing.name = fixture.name AND existing.currency = 'UAH');

    UPDATE account SET balance = (
        SELECT coalesce(sum(CASE WHEN transaction_type = 'income' THEN amount ELSE -amount END), 0)
        FROM "transaction" WHERE account_id = demo_account
    ) WHERE id = demo_account;
END $$;
COMMIT;

SELECT to_char(t.created_at AT TIME ZONE 'UTC', 'YYYY-MM') AS month,
       sum(t.amount) FILTER (WHERE t.transaction_type = 'income') AS income,
       sum(t.amount) FILTER (WHERE t.transaction_type = 'expense') AS expense,
       count(*) AS operations
FROM "transaction" t JOIN account a ON a.id = t.account_id JOIN public."user" u ON u.id = a.user_id
WHERE lower(u.email) = 'pavlohorokh4@gmail.com' AND a.name = '[Демо] Рахунок для перевірки кабінету'
GROUP BY month ORDER BY month;

SELECT s.name, s.amount, s.currency, s.billing_day
FROM subscription s JOIN public."user" u ON u.id = s.user_id
WHERE lower(u.email) = 'pavlohorokh4@gmail.com' AND s.name LIKE '[Демо]%'
ORDER BY s.billing_day;
