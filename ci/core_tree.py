#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Doc/loc/kiem cay source Odoo core cho mirror Todoo.

Chi dung thu vien chuan -> chay giong het nhau tren GitHub Actions (ubuntu)
va tren may dev Windows (venv odoo19). Khong pip install gi.

Dung:
    python core_tree.py scan     --tree <root> [--config sync_filter.json]
    python core_tree.py filter   --tree <root> [--config ...] [--apply]
    python core_tree.py validate --tree <root> [--config ...]

Exit code:
    0 = OK · 1 = gate DO (co van de) · 2 = sai tham so / khong doc duoc cay
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CONFIG = os.path.join(HERE, "sync_filter.json")


# ---------------------------------------------------------------- helpers


def load_config(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def addons_dirs(tree: str, cfg: dict) -> list[str]:
    out = []
    for rel in cfg["addons_roots"]:
        p = os.path.join(tree, rel.replace("/", os.sep))
        if os.path.isdir(p):
            out.append(p)
    if not out:
        die(f"Khong tim thay thu muc addons nao trong {tree} "
            f"(da thu: {cfg['addons_roots']})")
    return out


def read_manifest(mod_dir: str) -> dict | None:
    """Doc __manifest__.py an toan (literal_eval, khong exec)."""
    f = os.path.join(mod_dir, "__manifest__.py")
    if not os.path.isfile(f):
        return None
    try:
        with open(f, encoding="utf-8") as fh:
            return ast.literal_eval(fh.read())
    except Exception as exc:                      # manifest hong = tin xau
        return {"__parse_error__": str(exc)}


def collect_modules(roots: list[str]) -> dict[str, str]:
    """{ten_module: duong_dan}. Trung ten -> ban dau tien thang (giong Odoo)."""
    mods: dict[str, str] = {}
    for root in roots:
        for name in sorted(os.listdir(root)):
            path = os.path.join(root, name)
            if not os.path.isdir(path) or name.startswith("."):
                continue
            if os.path.isfile(os.path.join(path, "__manifest__.py")):
                mods.setdefault(name, path)
    return mods


def missing_deps(mods: dict[str, str]) -> dict[str, list[str]]:
    """{dep_thieu: [module dang can no]}"""
    out: dict[str, list[str]] = {}
    for name, path in mods.items():
        man = read_manifest(path) or {}
        if "__parse_error__" in man:
            continue
        for dep in man.get("depends", []):
            if dep not in mods:
                out.setdefault(dep, []).append(name)
    return out


def parse_errors(mods: dict[str, str]) -> dict[str, str]:
    out = {}
    for name, path in mods.items():
        man = read_manifest(path) or {}
        if "__parse_error__" in man:
            out[name] = man["__parse_error__"]
    return out


def walk_files(tree: str, suffix: str) -> list[str]:
    hits = []
    for base, dirs, files in os.walk(tree):
        dirs[:] = [d for d in dirs if d != ".git"]
        for f in files:
            if f.endswith(suffix):
                hits.append(os.path.join(base, f))
    return hits


def die(msg: str, code: int = 2) -> None:
    print(f"::error::{msg}" if os.environ.get("GITHUB_ACTIONS") else f"LOI: {msg}")
    sys.exit(code)


def section(title: str) -> None:
    print(f"\n=== {title} " + "=" * max(0, 60 - len(title)))


# ---------------------------------------------------------------- commands


def cmd_scan(tree: str, cfg: dict) -> int:
    roots = addons_dirs(tree, cfg)
    mods = collect_modules(roots)
    miss = missing_deps(mods)
    bad = parse_errors(mods)
    po = [p for p in walk_files(tree, ".po")]
    keep = set(cfg["keep_languages"]["files"])
    po_keep = [p for p in po if os.path.basename(p) in keep]
    l10n = sorted(m for m in mods if m.startswith("l10n_"))

    section("TONG QUAN")
    print(f"module            : {len(mods)}")
    print(f"l10n_* con lai    : {len(l10n)} -> {', '.join(l10n) or '(khong co)'}")
    print(f".po tong / giu lai: {len(po)} / {len(po_keep)}")
    print(f".pot              : {len(walk_files(tree, '.pot'))}")
    print(f"manifest hong     : {len(bad)}")
    print(f"dep thieu         : {len(miss)}")
    if miss:
        section("DEP THIEU")
        for dep, users in sorted(miss.items()):
            print(f"  {dep:34s} <- {len(users)} module: {', '.join(sorted(users)[:6])}")
    if bad:
        section("MANIFEST HONG")
        for name, err in bad.items():
            print(f"  {name}: {err}")
    return 0


def cmd_filter(tree: str, cfg: dict, apply: bool) -> int:
    roots = addons_dirs(tree, cfg)
    mode = "XOA THAT" if apply else "THU (dry-run, khong xoa gi)"
    print(f"Che do: {mode}\nCay   : {tree}")

    removed_po = removed_l10n = removed_orphan = 0

    # --- 1. .po ngoai danh sach giu (.pot LUON giu lai) -------------------
    keep = set(cfg["keep_languages"]["files"])
    for p in walk_files(tree, ".po"):
        if os.path.basename(p) not in keep:
            removed_po += 1
            if apply:
                os.remove(p)
    print(f"[1] .po xoa: {removed_po}  (giu: {', '.join(sorted(keep))} + toan bo .pot)")

    # --- 2. module l10n_* ngoai danh sach giu -----------------------------
    keep_l10n = set(cfg["keep_l10n"]["modules"])
    for root in roots:
        for name in sorted(os.listdir(root)):
            path = os.path.join(root, name)
            if (name.startswith("l10n_") and name not in keep_l10n
                    and os.path.isdir(path)):
                removed_l10n += 1
                if apply:
                    shutil.rmtree(path, ignore_errors=True)
    print(f"[2] l10n_* xoa: {removed_l10n}  (giu: {', '.join(sorted(keep_l10n))})")

    # --- 3. don module mo coi (lap toi khi sach) --------------------------
    po_cfg = cfg["prune_orphans"]
    if po_cfg.get("enabled") and apply:
        protect = set(po_cfg.get("protect", []))
        for rnd in range(1, int(po_cfg.get("max_rounds", 10)) + 1):
            mods = collect_modules(roots)
            miss = missing_deps(mods)
            victims = sorted({u for users in miss.values() for u in users} - protect)
            if not victims:
                print(f"[3] vong {rnd}: sach, dung.")
                break
            print(f"[3] vong {rnd}: xoa {len(victims)} mo coi -> "
                  f"{', '.join(victims[:8])}{' ...' if len(victims) > 8 else ''}")
            for v in victims:
                shutil.rmtree(mods[v], ignore_errors=True)
                removed_orphan += 1
        else:
            die("Don mo coi khong hoi tu sau max_rounds — cay co van de, dung lai.", 1)
    elif po_cfg.get("enabled"):
        mods = collect_modules(roots)
        n = len({u for users in missing_deps(mods).values() for u in users})
        print(f"[3] mo coi se xoa (uoc luong o dry-run): {n}")

    print(f"\nTONG: .po={removed_po} | l10n={removed_l10n} | mo_coi={removed_orphan}")
    _emit_gh_output({"removed_po": removed_po, "removed_l10n": removed_l10n,
                     "removed_orphan": removed_orphan})
    return 0


def cmd_validate(tree: str, cfg: dict) -> int:
    roots = addons_dirs(tree, cfg)
    mods = collect_modules(roots)
    fails: list[str] = []
    warns: list[str] = []

    # G-1 dependency khep kin
    miss = missing_deps(mods)
    if miss:
        detail = "; ".join(f"{d} <- {', '.join(sorted(u)[:3])}"
                           for d, u in sorted(miss.items())[:8])
        fails.append(f"G-1 dependency gay: {len(miss)} dep thieu ({detail})")

    # G-2 manifest doc duoc
    bad = parse_errors(mods)
    if bad:
        fails.append(f"G-2 manifest hong: {', '.join(sorted(bad)[:8])}")

    # G-3 module bat buoc con nguyen
    need = [m for m in cfg["required_modules"]["modules"] if m not in mods]
    if need:
        fails.append(f"G-3 mat module bat buoc: {', '.join(need)}")

    # G-4 khong con l10n ngoai danh sach
    keep_l10n = set(cfg["keep_l10n"]["modules"])
    stray = sorted(m for m in mods if m.startswith("l10n_") and m not in keep_l10n)
    if stray:
        fails.append(f"G-4 con l10n ngoai danh sach: {', '.join(stray[:8])}")

    # G-5 khong con .po ngoai danh sach
    keep_po = set(cfg["keep_languages"]["files"])
    stray_po = [p for p in walk_files(tree, ".po")
                if os.path.basename(p) not in keep_po]
    if stray_po:
        fails.append(f"G-5 con {len(stray_po)} file .po ngoai danh sach "
                     f"(vd {os.path.relpath(stray_po[0], tree)})")

    # G-6 nguong toi thieu — chong 'filter cat sach ma van xanh'
    mc = cfg["min_counts"]
    n_vi = len([p for p in walk_files(tree, ".po")])
    n_pot = len(walk_files(tree, ".pot"))
    if len(mods) < mc["modules"]:
        fails.append(f"G-6 chi con {len(mods)} module (< {mc['modules']}) — nghi filter cat nham")
    if n_vi < mc["vi_po_files"]:
        warns.append(f"G-6 chi con {n_vi} file .po (< {mc['vi_po_files']})")
    if n_pot < mc["pot_files"]:
        fails.append(f"G-6 chi con {n_pot} file .pot (< {mc['pot_files']}) — mat .pot la mat kha nang dich lai")

    section("KET QUA GATE")
    print(f"module={len(mods)} | l10n={sorted(m for m in mods if m.startswith('l10n_'))} "
          f"| po={n_vi} | pot={n_pot}")
    for w in warns:
        print(f"  CANH BAO: {w}")
    if fails:
        for f in fails:
            print(f"  DO: {f}")
        print("\nGATE DO -> KHONG duoc push ban nay len mirror.")
        return 1
    print("\nGATE XANH -> cay sach, khep kin dependency, du module bat buoc.")
    return 0


def _emit_gh_output(vals: dict) -> None:
    path = os.environ.get("GITHUB_OUTPUT")
    if not path:
        return
    with open(path, "a", encoding="utf-8") as fh:
        for k, v in vals.items():
            fh.write(f"{k}={v}\n")


# ---------------------------------------------------------------- main


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["scan", "filter", "validate"])
    ap.add_argument("--tree", required=True, help="Thu muc goc cay Odoo core")
    ap.add_argument("--config", default=DEFAULT_CONFIG)
    ap.add_argument("--apply", action="store_true",
                    help="filter: xoa that (mac dinh la dry-run)")
    args = ap.parse_args()

    if not os.path.isdir(args.tree):
        die(f"Khong thay cay: {args.tree}")
    cfg = load_config(args.config)

    if args.command == "scan":
        return cmd_scan(args.tree, cfg)
    if args.command == "filter":
        return cmd_filter(args.tree, cfg, args.apply)
    return cmd_validate(args.tree, cfg)


if __name__ == "__main__":
    sys.exit(main())
