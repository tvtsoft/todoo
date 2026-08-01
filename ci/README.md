# CI sync core — cài đặt & vận hành

Bộ 3 file này là **cổng vào duy nhất** của mã Odoo core đi vào hệ thống Todoo.
Nếu nó sai, mọi thứ phía sau (release train, tenant) sai theo.

| File | Vai trò |
|---|---|
| `sync_filter.json` | **Chính sách** — giữ ngôn ngữ nào, l10n nào, module nào bắt buộc phải còn. Sửa file này, đừng sửa script. |
| `core_tree.py` | **Cỗ máy** — `scan` (xem), `filter` (lọc), `validate` (gác). Chỉ dùng thư viện chuẩn. |
| `../.github/workflows/odoo-sync-core.yml` | **Lịch chạy** — GitHub Actions, hàng tuần. |

Bản gốc của bộ này nằm ở workspace eCoMTA: `OSHM/docs/git_setting/` (kèm thiết kế tổng thể).

---

## 1. Bật lần đầu (làm một lần)

1. **Settings → Actions → General → Workflow permissions** = *Read and write*.
   Không bật thì bước push sẽ hỏng — mặc định GitHub giờ là read-only.
2. Tạo sẵn nhánh đích promote: `18.0-dev`, `19.0-dev`.
3. Chạy tay một lần với **`dry_run = true`**, đọc phần Summary. Chỉ khi số liệu hợp lý mới chạy thật.

> **Nhánh `master` trong repo này là rác** do workflow cũ đẩy nguyên Odoo master lên.
> Xoá được (`git push origin --delete master`) — không có gì phụ thuộc vào nó.

## 2. Sơ đồ nhánh

```text
github.com/odoo/odoo  ──(Actions, tự động, hàng tuần)──►  19.0-upstream   ← CHỈ bot ghi
                                                               │  PR tự mở, bạn duyệt
                                                               ▼
                                                          19.0-dev        ← bạn làm việc
                                                               ▼ PR
                                                          19.0-sandbox
                                                               ▼ PR (protected)
                                                          19.0-prod
```

**Bot không bao giờ chạm nhánh nào ngoài `*-upstream`.** Đây là tính chất an toàn quan trọng
nhất của thiết kế này: một lỗi trong workflow không thể xoá mất việc của bạn.

## 3. Dùng tay trên máy dev

```bash
# Xem cây hiện tại có gì (không sửa gì)
python core_tree.py scan --tree D:/ect/ecomta/versions/19.0/odoo/odoo

# Thử lọc, chưa xoá
python core_tree.py filter --tree <cây>

# Xoá thật
python core_tree.py filter --tree <cây> --apply

# Gác: 0 = sạch, 1 = có vấn đề
python core_tree.py validate --tree <cây>
```

Trên Windows dùng `D:\ect\ecomta\venv\odoo19\Scripts\python.exe`.

## 4. Sáu phép gác (`validate`)

| Mã | Kiểm | Vì sao có nó |
|----|------|--------------|
| G-1 | Không còn dependency gãy | Bộ lọc `l10n_*` bỏ sót module có `l10n_` ở **giữa** tên (`documents_l10n_be_hr_payroll`) → chúng thành mồ côi |
| G-2 | Mọi `__manifest__.py` đọc được | Manifest hỏng = module biến mất âm thầm |
| G-3 | Còn đủ module bắt buộc | Chống bộ lọc cắt nhầm thứ sống còn |
| G-4 | Không còn `l10n_` lạ | Bộ lọc chạy đủ |
| G-5 | Không còn `.po` ngoài danh sách | Bộ lọc chạy đủ |
| G-6 | Ngưỡng tối thiểu (module / .po / .pot) | Chống ca tệ nhất: **cắt sạch cả cây mà vẫn báo xanh** |

**G-6 tồn tại vì một lý do cụ thể:** mất `.pot` là mất khả năng dịch lại — mà mất im lặng,
không có gì báo. Cổng nào không đỏ được thì không phải cổng.

## 5. Đổi chính sách lọc

Sửa `sync_filter.json` → PR → Actions chạy lại → gate xác nhận. Không sửa thẳng lên nhánh mặc định.

Hai ca hay gặp:

- **Thêm nước:** có KH FDI cần Nhật → thêm `"ja.po"` vào `keep_languages.files` và `"l10n_jp"` vào `keep_l10n.modules`.
- **Odoo tách module mới:** gate G-3 đỏ vì thiếu module bắt buộc → đọc changelog Odoo trước khi nới danh sách. **Đừng nới cho xanh.**

## 6. Điều tuyệt đối không làm

- ❌ Không sửa `vi.po` của core — sync tuần sau ghi đè mất. Bản dịch của mình để ở module override riêng.
- ❌ Không `--force` push lên `*-upstream` — mất merge-base là mất luôn đường promote.
- ❌ Không nới `required_modules` / `min_counts` chỉ để cho gate xanh.
- ❌ Không đặt module custom vào trong cây core — `rsync --delete` sẽ xoá sạch ở lần sync kế.
