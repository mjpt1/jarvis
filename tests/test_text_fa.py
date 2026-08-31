from jarvis.text_fa import (
    fuzzy_contains, normalize, parse_duration_seconds, words_to_number,
    extract_reminder_message,
)


def test_normalize_unifies_chars_and_digits():
    assert normalize("كتاب ي ۱۲۳") == "کتاب ی 123"
    assert normalize("سلاااام") == "سلاام"
    assert normalize("  چند   تا  ") == "چند تا"


def test_words_to_number_simple():
    assert words_to_number("پنج") == 5
    assert words_to_number("ده") == 10
    assert words_to_number("42") == 42


def test_words_to_number_compound():
    assert words_to_number("بیست و پنج") == 25
    assert words_to_number("صد و ده") == 110
    assert words_to_number("یک هزار و دویست") == 1200


def test_parse_duration_seconds():
    assert parse_duration_seconds("ده دقیقه دیگه") == 600
    assert parse_duration_seconds("۹۰ ثانیه") == 90
    assert parse_duration_seconds("یک ساعت") == 3600
    assert parse_duration_seconds("نیم ساعت") == 1800
    assert parse_duration_seconds("هیچی اینجا نیست") is None


def test_fuzzy_contains_tolerates_spelling():
    assert fuzzy_contains("جارویس اهنگ پخش کن", "اهنگ پخش کن")
    assert fuzzy_contains("لطفا ساعت چنده", "ساعت چنده")
    assert not fuzzy_contains("برو بیرون", "اهنگ پخش کن")


def test_extract_reminder_message():
    assert extract_reminder_message("ده دقیقه دیگه یادم بنداز آب بخورم") == "اب بخورم"
