#!/usr/bin/env python3
from pathlib import Path

path = Path(__file__).resolve().parents[1] / 'medical_channel_pipeline' / 'ccgp_detail.py'
source = path.read_text(encoding='utf-8')

start = source.index('def _extract_registration_deadline(text: str) -> str:\n')
end = source.index('\ndef _extract_bid_deadline(text: str) -> str:\n', start)
new_registration = '''def _extract_registration_deadline(text: str) -> str:
    # Liaoning's official procurement template commonly numbers this as
    # section four and publishes exact start/end datetimes instead of a
    # daily business-hours schedule. Prefer that exact official end time.
    direct_patterns = [
        r"(?:三|四)[、.]\\s*获取(?:招标|采购)文件\\s+时间\\s*[：:]\\s*"
        r"20\\d{2}年\\d{1,2}月\\d{1,2}日\\s*\\d{1,2}\\s*(?:时|点)\\s*\\d{1,2}\\s*分?\\s*(?:到|至)\\s*"
        r"(20\\d{2})年(\\d{1,2})月(\\d{1,2})日\\s*(\\d{1,2})\\s*(?:时|点)\\s*(\\d{1,2})\\s*分?",
        r"(?:三|四)[、.]\\s*获取(?:招标|采购)文件\\s+时间\\s*[：:]\\s*"
        r"20\\d{2}年\\d{1,2}月\\d{1,2}日\\s*\\d{1,2}\\s*[：:]\\s*\\d{2}\\s*(?:到|至)\\s*"
        r"(20\\d{2})年(\\d{1,2})月(\\d{1,2})日\\s*(\\d{1,2})\\s*[：:]\\s*(\\d{2})",
    ]
    for pattern in direct_patterns:
        direct = re.search(pattern, text, re.S)
        if direct:
            return _datetime_from_cn(*direct.groups())

    patterns = [
        r"(?:三|四)[、.]\\s*获取(?:招标|采购)文件\\s+时间\\s*[：:]\\s*"
        r"20\\d{2}年\\d{1,2}月\\d{1,2}日\\s*(?:到|至)\\s*"
        r"(20\\d{2})年(\\d{1,2})月(\\d{1,2})日"
        r"(.+?)(?:地点\\s*[：:]|(?:四|五)[、.])",
        r"(?:三|四)[、.]\\s*获取(?:招标|采购)文件\\s+时间\\s*[：:]\\s*"
        r"20\\d{2}-\\d{1,2}-\\d{1,2}\\s*(?:到|至)\\s*"
        r"(20\\d{2})-(\\d{1,2})-(\\d{1,2})"
        r"(.+?)(?:地点\\s*[：:]|(?:四|五)[、.])",
    ]
    section = None
    for pattern in patterns:
        section = re.search(pattern, text, re.S)
        if section:
            break
    if not section:
        raise CcgpDetailParseError("CCGP_REGISTRATION_SECTION_NOT_FOUND")
    year, month, day, schedule = section.groups()

    if "下午" in schedule:
        afternoon_schedule = schedule.rsplit("下午", 1)[1]
        afternoon_times = re.findall(r"至\\s*(\\d{1,2})\\s*[：:]\\s*(\\d{2})", afternoon_schedule)
        if not afternoon_times:
            raise CcgpDetailParseError("CCGP_REGISTRATION_END_TIME_NOT_FOUND")
        hour, minute = afternoon_times[-1]
    else:
        times = re.findall(r"至\\s*(\\d{1,2})\\s*[：:]\\s*(\\d{2})", schedule)
        if not times:
            raise CcgpDetailParseError("CCGP_REGISTRATION_END_TIME_NOT_FOUND")
        hour, minute = times[-1]
    return _datetime_from_cn(year, month, day, hour, minute)
'''
source = source[:start] + new_registration + source[end:]

old_bid = 'r"四[、.]\\s*提交投标文件截止时间、开标时间和地点\\s*"'
new_bid = 'r"(?:四|五)[、.]\\s*提交投标文件截止时间、开标时间和地点\\s*"'
if source.count(old_bid) != 1:
    raise SystemExit('bid section prefix did not match exactly once')
source = source.replace(old_bid, new_bid)

old_registration_locator = '("facts.registration_deadline", "三、获取采购文件/时间" if procurement_method != "公开招标" else "三、获取招标文件/时间"),'
new_registration_locator = '("facts.registration_deadline", "获取采购文件/时间" if procurement_method != "公开招标" else "获取招标文件/时间"),'
if source.count(old_registration_locator) != 1:
    raise SystemExit('registration locator did not match exactly once')
source = source.replace(old_registration_locator, new_registration_locator)

old_bid_locator = 'deadline_locator="四、提交投标文件截止时间、开标时间和地点",'
new_bid_locator = 'deadline_locator="提交投标文件截止时间、开标时间和地点",'
if source.count(old_bid_locator) != 1:
    raise SystemExit('public tender deadline locator did not match exactly once')
source = source.replace(old_bid_locator, new_bid_locator)

path.write_text(source, encoding='utf-8')
print('patched Liaoning CCGP template support')
