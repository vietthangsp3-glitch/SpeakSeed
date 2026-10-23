# Data attribution

Ngân hàng từ vựng SpeakSeed là dữ liệu dẫn xuất được ghép từ các nguồn mở dưới đây. Bảng `data_sources` lưu phiên bản, URL, giấy phép, ngày lấy và SHA-256; bảng `word_attributions` lưu nguồn của từng nhóm trường cho mỗi từ.

## CEFR-J Wordlist 1.5

- Nguồn: <https://github.com/openlanguageprofiles/olp-en-cefrj>
- Chủ sở hữu/ghi công: The CEFR-J Wordlist Version 1.5, Tono Laboratory, Tokyo University of Foreign Studies.
- Điều khoản: được dùng cho nghiên cứu và thương mại khi ghi rõ nguồn theo phần “Terms of use” của dự án.
- Trường sử dụng: headword, loại từ và cấp CEFR.

## Skypedia English–Vietnamese Dictionary

- Nguồn: <https://github.com/skypediacode/english-vietnamese-dictionary>
- Giấy phép: CC BY-SA 4.0.
- Ghi công: Skypedia English–Vietnamese Dictionary và các dự án nguồn được ghi trong README của kho dữ liệu.
- Trường sử dụng: nghĩa tiếng Việt và IPA.

Phần dữ liệu dẫn xuất từ nguồn này phải tiếp tục tuân thủ yêu cầu attribution và share-alike của CC BY-SA 4.0.

## Vietnamese Wiktionary qua Kaikki/Wiktextract

- Nguồn mục từ: <https://vi.wiktionary.org/>; trang nguồn của từng mục từ được lưu trong `provenance_json` và `word_attributions`.
- Bản trích xuất: <https://kaikki.org/viwiktionary/rawdata.html>.
- Snapshot: viwiktionary dump `2026-10-02`, trích xuất `2026-10-21` bằng Wiktextract `c1bb342` và Wikitextprocessor `6f96ddf`.
- SHA-256 file JSONL gzip local: `dcdaf93d642ae1d1c4d495b68d90eb572fac86d00281044cf804e0d98147a25e`.
- Giấy phép áp dụng cho các trường văn bản được tái sử dụng: [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/). Điều khoản Wikimedia cho phép người tái sử dụng tuân theo CC BY-SA hoặc GFDL đối với nội dung song giấy phép; SpeakSeed chọn nhánh CC BY-SA 4.0.
- Ghi công: Vietnamese Wiktionary contributors; machine-readable extraction by Kaikki.org/Wiktextract (Tatu Ylonen).
- Thay đổi của SpeakSeed: chọn mục từ tiếng Anh, chọn nghĩa chính phù hợp part of speech, chuẩn hóa khoảng trắng và bỏ ghi chú niên đại dạng ngoặc vuông. Nghĩa được đưa vào hàng đợi kiểm duyệt; không tự gắn `human_reviewed`.

Các trường từ điển được chuyển thể từ nguồn này được phân phối theo CC BY-SA 4.0. Khi xuất bản, SpeakSeed phải giữ URL trang nguồn, liên kết giấy phép, thông báo thay đổi và không áp dụng hạn chế bổ sung lên chính các trường dữ liệu CC BY-SA đó. Nội dung trang hoặc media có thông báo giấy phép riêng không được nhập tự động.

## Tatoeba Vietnamese–English selection

- Nguồn tuyển chọn: <https://www.manythings.org/anki/>
- Nguồn câu gốc: <https://tatoeba.org/>
- Snapshot: 2026-02-13.
- Giấy phép được công bố cho gói: CC BY 2.0 FR.
- Ghi công: Tatoeba contributors; gói tuyển chọn do ManyThings.org phân phối.
- Trường sử dụng: câu ví dụ Anh–Việt và ID dòng nguồn.

## FLORES-200

- Nguồn: <https://github.com/facebookresearch/flores>
- Phiên bản dữ liệu: 2022-07.
- Giấy phép: CC BY-SA 4.0.
- Ghi công: FLORES-200, Meta AI / No Language Left Behind contributors.
- Trường sử dụng: câu song song tiếng Anh–Việt.

## NTREX-128

- Nguồn: <https://github.com/MicrosoftTranslator/NTREX>
- Snapshot: 2022-11-24.
- Giấy phép: CC BY-SA 4.0.
- Ghi công: NTREX-128 by Microsoft Translator and the WMT19 contributors.
- Trường sử dụng: câu song song tiếng Anh–Việt.

## Cách truy vết một từ

```sql
SELECT w.word, a.field_name, a.source_name, a.source_record_id,
       a.source_url, a.license_name, a.attribution
FROM library_words AS w
JOIN word_attributions AS a ON a.word_id = w.id
WHERE w.normalized_word = 'example';
```

Mỗi từ đã xuất bản hiện có ba nhóm attribution: `level,pos`, `meaning,ipa`, và `example,example_vi`. Nội dung không đủ nguồn hoặc thiếu một trường bắt buộc bị loại khỏi tập xuất bản.

## Chương trình bốn kỹ năng giai đoạn 4

Toàn bộ transcript Listening, bài Reading, tình huống Speaking, đề Writing và câu hỏi đi kèm trong bảng `skill_lessons`/`skill_questions` được biên soạn riêng cho SpeakSeed, không sao chép từ nguồn bên ngoài.

- Nguồn lưu trong database: `SpeakSeed original four-skills curriculum v1`.
- Giấy phép lưu trong database: `Project-owned original content`.
- Trạng thái QA: `automated_checked`.
- Trạng thái `human_reviewed` không được gắn cho bất kỳ bài nào trong đợt này.

Nếu bổ sung bài đọc hoặc audio từ bên ngoài trong tương lai, nguồn, giấy phép và attribution phải được xác minh trước khi đặt `published=1`.
