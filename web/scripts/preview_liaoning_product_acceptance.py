from __future__ import annotations

import re
import sys
import time
from pathlib import Path


def apply_patch() -> None:
    path = Path('web/scripts/preview_add_liaoning_product_lists.py')
    source = path.read_text(encoding='utf-8')
    prefix, rest = source.split("TEST.write_text(r'''", 1)
    body, suffix = rest.rsplit("''', encoding='utf-8')", 1)
    body, count = re.subn(
        r"text = '''(.*?)'''",
        lambda match: 'text = """' + match.group(1) + '"""',
        body,
        flags=re.S,
    )
    if count != 3:
        raise SystemExit(f'STAGING_TEST_STRING_COUNT_MISMATCH:{count}')
    fixed = prefix + "TEST.write_text(r'''" + body + "''', encoding='utf-8')" + suffix
    compile(fixed, str(path), 'exec')
    namespace = {'__name__': '__main__', '__file__': str(path)}
    exec(compile(fixed, str(path), 'exec'), namespace)


def live_verify() -> None:
    root = Path('web/pipeline').resolve()
    sys.path.insert(0, str(root))
    from medical_channel_pipeline.ccgp_detail import (  # noqa: PLC0415
        fetch_ccgp_detail_html,
        parse_ccgp_public_tender_html,
    )

    observed_at = '2026-09-09T00:00:00+00:00'

    def parse(label: str, opportunity_id: str, url: str) -> list[tuple[str, str]]:
        html = fetch_ccgp_detail_html(url)
        record = parse_ccgp_public_tender_html(
            html,
            source_url=url,
            observed_at=observed_at,
            opportunity_id=opportunity_id,
        )
        pairs = [
            (str(item.get('raw_name') or ''), str(item.get('quantity') or ''))
            for item in record['facts'].get('product_items') or []
        ]
        print(label, len(pairs), pairs)
        return pairs

    jinqiu = parse(
        'jinqiu-endoscopy',
        'ccgp_ln_1a3880ab31870644',
        'https://www.ccgp.gov.cn/cggg/dfgg/gkzb/202609/t20260908_27291255.htm',
    )
    expected_jinqiu = [
        ('超声主机', '1台'),
        ('超声电子上消化道内窥镜（扇扫）', '1条'),
        ('超声电子上消化道内窥镜（环扫）', '1条'),
        ('高清电子内窥镜系统', '1套'),
    ]
    if jinqiu != expected_jinqiu:
        raise SystemExit(f'JINQIU_PRODUCTS_MISMATCH:{jinqiu!r}')

    time.sleep(4.0)
    yuhong = parse(
        'yuhong-tb-equipment',
        'ccgp_ln_e098f4b20ac83f0c',
        'https://www.ccgp.gov.cn/cggg/dfgg/gkzb/202609/t20260908_27291252.htm',
    )
    expected_yuhong_prefix = [
        ('结核分枝杆菌耐药基因检测多通道分析仪', '1台'),
        ('高压蒸汽灭菌器', '1台'),
        ('生物安全柜', '1个'),
    ]
    if yuhong[:3] != expected_yuhong_prefix or len(yuhong) < 3:
        raise SystemExit(f'YUHONG_PRODUCTS_MISMATCH:{yuhong!r}')

    time.sleep(4.0)
    yingkou = parse(
        'yingkou-operating-room',
        'ccgp_ln_be60c73331219966',
        'https://www.ccgp.gov.cn/cggg/dfgg/gkzb/202609/t20260908_27288084.htm',
    )
    if len(yingkou) != 47:
        raise SystemExit(f'YINGKOU_PRODUCT_COUNT_MISMATCH:{len(yingkou)}')
    required_yingkou = {
        ('负极板回路垫', '2套'),
        ('电动综合手术床', '4张'),
        ('高频电刀', '4台'),
        ('麻醉机', '4台'),
        ('病人监护仪', '3台'),
        ('抓钳4', '2把'),
    }
    if not required_yingkou.issubset(set(yingkou)):
        raise SystemExit(f'YINGKOU_REQUIRED_PRODUCTS_MISSING:{yingkou!r}')

    time.sleep(4.0)
    attachment_only = parse(
        'huludao-attachment-only',
        'ccgp_ln_340f7081b4500696',
        'https://www.ccgp.gov.cn/cggg/dfgg/gkzb/202609/t20260908_27285310.htm',
    )
    if attachment_only:
        raise SystemExit(f'ATTACHMENT_ONLY_PRODUCTS_INVENTED:{attachment_only!r}')


if __name__ == '__main__':
    if len(sys.argv) != 2 or sys.argv[1] not in {'apply', 'live'}:
        raise SystemExit('usage: preview_liaoning_product_acceptance.py [apply|live]')
    if sys.argv[1] == 'apply':
        apply_patch()
    else:
        live_verify()
