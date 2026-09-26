from pathlib import Path


def test_calendar_uses_explicit_utf8_even_with_windows_legacy_locale(monkeypatch):
    from jinshu.tools import source
    original = Path.read_text
    seen = []
    def checked(path, *args, **kwargs):
        if path.name == 'calendar.json':
            assert kwargs.get('encoding') in ('utf-8', 'utf-8-sig')
            seen.append(path.name)
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'read_text', checked)
    assert '模拟营业日历' in source('calendar.json')['note']
    assert seen == ['calendar.json']
