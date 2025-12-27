# PR Code Reviewer

GitHub'da açılan pull request'leri otomatik olarak analiz eden, yapay zeka tabanlı kod inceleme aracı. Yazılan kodda hataları bulur, güvenlik sorunlarını tespit eder ve geliştirme önerileri sunar.

## Ne İşe Yaradığı

Bu araç üç yoldan kullanılabilir. Birincisi, kod farkını doğrudan sisteme gönderip tahlil ettirmek. İkincisi, GitHub'dan otomatik olarak pull request'i çekerek incelemek ve sonuçları yorum olarak yazmak. Üçüncüsü ise webhook aracılığıyla PR açıldığında sistem otomatik olarak devreye girmek ve değerlendirme yapmak.

## Kurulum Adımları

```bash
pip install -r requirements.txt
```

```
GITHUB_TOKEN=github_tokeniniz
GEMINI_API_KEY=gemini_anahtarınız
GITHUB_WEBHOOK_SECRET=webhook_sifresi
```

## Nasıl Çalıştırılır

```bash
uvicorn app.main:app --reload
```

Sistem 8000 numaralı portta açılacak ve şu işlemleri yapabileceksiniz:

**Durumu Kontrol Etme:**
```bash
curl http://localhost:8000/health
```

**Kod Farkını Analiz Etme:**
```bash
curl -X POST http://localhost:8000/local-review \
  -H "Content-Type: application/json" \
  -d '{
    "diff_text": "--- a/dosya.py\n+++ b/dosya.py\n...",
    "review_types": ["short_summary", "bug_detection"]
  }'
```

**GitHub'dan Pull Request İnceleme:**
```bash
curl -X POST http://localhost:8000/github-review \
  -H "Content-Type: application/json" \
  -d '{
    "owner": "kullaniciadi",
    "repo": "depo-adi",
    "pr_number": 1
  }'
```

**İstatistikleri Görme:**
```bash
curl http://localhost:8000/stats
```

## Docker ile Çalıştırma

Sabit bir ortamda çalıştırmak için Docker kullanabilirsiniz:

```bash
docker build -t pr-code-reviewer .

docker run -p 8000:8000 \
  -e GITHUB_TOKEN=tokeniniz \
  -e GEMINI_API_KEY=anahtarınız \
  pr-code-reviewer
```

## İç Yapısı

Proje üç ana bölümden oluşmaktadır. İlk olarak `reviewer.py` dosyası analiz işlemini iki aşamada gerçekleştirir: Birinci aşamada hızlı bir özet oluşturur, ikinci aşamada daha ayrıntılı inceleme yapar. İkinci olarak `json_parser.py` yapay zekanın verdiği cevapları beş farklı yöntemle ayrıştırır ve hatalı formatlı yanıtları da düzeltir. Üçüncü olarak `github_client.py` GitHub API'siyle iletişim kurarak pull request bilgilerini alır ve yorum yazmakla görevlidir.

## Analiz Türleri

Sistem dört farklı açıdan kod incelemesi yapar. Değişiklik özeti ve önem derecesini belirler. Yazılan kodda olabilecek hataları ve mantık sorunlarını bulur. Güvenlik açıklarını ve veri koruma eksikliklerini tespit eder. Son olarak performans sorunlarını tanıyarak iyileştirme önerileri sunar.

## Test Etme

```bash
pytest tests/ -v
```

Sistemde 24 adet test vardır ve hepsi başarıyla geçmektedir. Bunlar schema doğrulaması, parser sağlamlığı ve farklı kod durumlarını kapsamaktadır.

## Otomatikleştirme

GitHub Actions kullanarak code push olduğunda otomatik testler yapılır. Main branch'e commit atıldığında Docker image hazırlanır ve saklanır. Bu sayede yapılan değişiklikler kontrol edilir ve üretim ortamına hazır hale getirilir.
