"""
Unified diff parser — Semgrep bulgularını yalnızca PR'de gerçekten
değişen satırlarla sınırlamak için kullanılır.

GitHub'ın `.diff` formatında döndürdüğü unified diff'i parse eder ve
her dosya için "yeni dosyadaki hangi satır numaraları eklendi/değişti"
bilgisini çıkarır. Bu olmadan Semgrep, dosyadaki PR'den önce de var olan
bulguları da rapor eder — bu da gürültü ve "bu PR'nin suçu değil" tepkisine
yol açar.
"""

import re
from typing import Dict, Set

_FILE_HEADER_RE = re.compile(r"^\+\+\+ b/(.+)$")
_HUNK_HEADER_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")


def parse_added_lines(diff_text: str) -> Dict[str, Set[int]]:
    """
    Unified diff'i parse edip her dosya için eklenen/değişen satır
    numaralarını (yeni dosyadaki numaralandırmayla) döndürür.

    Args:
        diff_text: `git diff` / GitHub `.diff` formatında unified diff

    Returns:
        {dosya_yolu: {satır_no, ...}} — silinen dosyalar veya sadece
        silme içeren hunk'lar için boş set olabilir.
    """
    result: Dict[str, Set[int]] = {}
    current_file: str = None
    current_line: int = 0

    for raw_line in diff_text.splitlines():
        file_match = _FILE_HEADER_RE.match(raw_line)
        if file_match:
            current_file = file_match.group(1)
            if current_file == "dev/null":
                current_file = None
            else:
                result.setdefault(current_file, set())
            continue

        hunk_match = _HUNK_HEADER_RE.match(raw_line)
        if hunk_match:
            current_line = int(hunk_match.group(1))
            continue

        if current_file is None:
            continue

        if raw_line.startswith("+++") or raw_line.startswith("---"):
            continue
        elif raw_line.startswith("+"):
            result[current_file].add(current_line)
            current_line += 1
        elif raw_line.startswith("-"):
            # Silinen satır — yeni dosyada karşılığı yok, sayaç ilerlemez
            continue
        elif raw_line.startswith("\\"):
            # "\ No newline at end of file" — satır sayılmaz
            continue
        else:
            # Context (değişmeyen) satır — yeni dosyada da var
            current_line += 1

    return result
