def add(a, b):
    # tip kontrolü eklendi
    if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
        raise TypeError("sayı bekleniyor")
    return a + b
