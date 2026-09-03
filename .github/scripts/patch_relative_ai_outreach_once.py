from pathlib import Path


def patch(path_str: str, replacements: list[tuple[str, str, str]]) -> None:
    path = Path(path_str)
    source = path.read_text(encoding='utf-8')
    for old, new, label in replacements:
        count = source.count(old)
        if count != 1:
            raise SystemExit(f'{path_str}:{label}: expected exactly one match, got {count}')
        source = source.replace(old, new, 1)
    path.write_text(source, encoding='utf-8')


patch('web/api/ai/_analyzeCore.js', [
    (
        "const SOURCE_CATEGORY_TITLE_CONFLICT = 'SOURCE_CATEGORY_TITLE_CONFLICT'\n",
        "const SOURCE_CATEGORY_TITLE_CONFLICT = 'SOURCE_CATEGORY_TITLE_CONFLICT'\nconst RELATIVE_WINDOW_FLAG = 'RELATIVE_REGISTRATION_WINDOW_7_DAYS'\n",
        'relative-flag',
    ),
    (
        "function shanghaiDateString(nowMs) {\n  const parts = new Intl.DateTimeFormat('en-US', {\n    timeZone: SHANGHAI_TIME_ZONE,\n    year: 'numeric',\n    month: '2-digit',\n    day: '2-digit',\n  }).formatToParts(new Date(nowMs))\n  const values = Object.fromEntries(parts.map((part) => [part.type, part.value]))\n  return `${values.year}-${values.month}-${values.day}`\n}\n\nexport function runtimeWindowStatus(facts, nowMs = Date.now()) {\n  const registrationDeadline = parsedTime(facts.registration_deadline)\n  const registrationDate = /^\\d{4}-\\d{2}-\\d{2}$/.test(facts.registration_deadline_date || '')\n    ? facts.registration_deadline_date\n    : null\n  const bidDeadline = parsedTime(facts.bid_deadline)\n  const dateOnlyRegistrationClosed = registrationDate\n    ? shanghaiDateString(nowMs) > registrationDate\n    : false\n  const exactRegistrationClosed = registrationDeadline !== null && registrationDeadline <= nowMs\n\n  if (bidDeadline !== null && bidDeadline <= nowMs) return 'CLOSED'\n  if (bidDeadline === null && (exactRegistrationClosed || dateOnlyRegistrationClosed)) return 'CLOSED'\n  if (\n    bidDeadline !== null &&\n    bidDeadline > nowMs &&\n    (exactRegistrationClosed || dateOnlyRegistrationClosed)\n  ) {\n    return 'LATE_WINDOW'\n  }\n  return 'OPEN'\n}\n",
        "function shanghaiDateString(nowMs) {\n  const parts = new Intl.DateTimeFormat('en-US', {\n    timeZone: SHANGHAI_TIME_ZONE,\n    year: 'numeric',\n    month: '2-digit',\n    day: '2-digit',\n  }).formatToParts(new Date(nowMs))\n  const values = Object.fromEntries(parts.map((part) => [part.type, part.value]))\n  return `${values.year}-${values.month}-${values.day}`\n}\n\nfunction hasRelativeRegistrationWindow(facts) {\n  return Array.isArray(facts?.quality_flags) && facts.quality_flags.includes(RELATIVE_WINDOW_FLAG)\n}\n\nfunction addDaysDateString(value, days) {\n  const match = typeof value === 'string' ? value.match(/^(20\\d{2})-(\\d{2})-(\\d{2})/) : null\n  if (!match) return null\n  const date = new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3])))\n  if (Number.isNaN(date.getTime())) return null\n  date.setUTCDate(date.getUTCDate() + days)\n  return date.toISOString().slice(0, 10)\n}\n\nexport function runtimeWindowStatus(facts, nowMs = Date.now()) {\n  const registrationDeadline = parsedTime(facts.registration_deadline)\n  const registrationDate = /^\\d{4}-\\d{2}-\\d{2}$/.test(facts.registration_deadline_date || '')\n    ? facts.registration_deadline_date\n    : null\n  const bidDeadline = parsedTime(facts.bid_deadline)\n  const currentShanghaiDate = shanghaiDateString(nowMs)\n  const dateOnlyRegistrationClosed = registrationDate\n    ? currentShanghaiDate > registrationDate\n    : false\n  const exactRegistrationClosed = registrationDeadline !== null && registrationDeadline <= nowMs\n\n  if (bidDeadline !== null && bidDeadline <= nowMs) return 'CLOSED'\n  if (bidDeadline === null && (exactRegistrationClosed || dateOnlyRegistrationClosed)) return 'CLOSED'\n  if (\n    bidDeadline !== null &&\n    bidDeadline > nowMs &&\n    (exactRegistrationClosed || dateOnlyRegistrationClosed)\n  ) {\n    return 'LATE_WINDOW'\n  }\n\n  if (\n    registrationDeadline === null &&\n    registrationDate === null &&\n    bidDeadline === null &&\n    hasRelativeRegistrationWindow(facts)\n  ) {\n    const relativeEndDate = addDaysDateString(facts.publish_date, 7)\n    if (!relativeEndDate) return 'CLOSED'\n    return currentShanghaiDate > relativeEndDate ? 'CLOSED' : 'RELATIVE_WINDOW'\n  }\n\n  return 'OPEN'\n}\n",
        'runtime-window-status',
    ),
    (
        '    return parseDecisionContent(content)\n',
        "    return parseDecisionContent(content, {\n      relativeRegistrationWindow: windowStatus === 'RELATIVE_WINDOW',\n    })\n",
        'relative-output-validation',
    ),
])

patch('web/api/ai/analyze.js', [
    (
        "const MAX_VERIFIED_SNAPSHOT_FUTURE_SKEW_MS = 10 * 60 * 1000\n",
        "const MAX_VERIFIED_SNAPSHOT_FUTURE_SKEW_MS = 10 * 60 * 1000\nconst RELATIVE_WINDOW_FLAG = 'RELATIVE_REGISTRATION_WINDOW_7_DAYS'\n",
        'relative-flag',
    ),
    (
        "function chinaDateKey(now = Date.now()) {\n  const parts = new Intl.DateTimeFormat('en-US', {\n    timeZone: 'Asia/Shanghai',\n    year: 'numeric',\n    month: '2-digit',\n    day: '2-digit',\n  }).formatToParts(new Date(now))\n  const values = Object.fromEntries(parts.map((part) => [part.type, part.value]))\n  return `${values.year}-${values.month}-${values.day}`\n}\n\nfunction outreachWindow(facts) {\n  const now = Date.now()\n  const bid = parsedTime(facts?.bid_deadline)\n  const registration = parsedTime(facts?.registration_deadline)\n  const registrationDate = typeof facts?.registration_deadline_date === 'string'\n    ? facts.registration_deadline_date\n    : null\n  const registrationDateClosed = Boolean(\n    registrationDate && /^\\d{4}-\\d{2}-\\d{2}$/.test(registrationDate) && registrationDate < chinaDateKey(now),\n  )\n  if (bid !== null && bid <= now) return { open: false, late: false }\n  if (bid === null && ((registration !== null && registration <= now) || registrationDateClosed)) {\n    return { open: false, late: false }\n  }\n  const late = Boolean(\n    bid !== null && bid > now &&\n    ((registration !== null && registration <= now) || registrationDateClosed),\n  )\n  return { open: true, late }\n}\n",
        "function chinaDateKey(now = Date.now()) {\n  const parts = new Intl.DateTimeFormat('en-US', {\n    timeZone: 'Asia/Shanghai',\n    year: 'numeric',\n    month: '2-digit',\n    day: '2-digit',\n  }).formatToParts(new Date(now))\n  const values = Object.fromEntries(parts.map((part) => [part.type, part.value]))\n  return `${values.year}-${values.month}-${values.day}`\n}\n\nfunction hasRelativeRegistrationWindow(facts) {\n  return Array.isArray(facts?.quality_flags) && facts.quality_flags.includes(RELATIVE_WINDOW_FLAG)\n}\n\nfunction addDaysDateKey(value, days) {\n  const match = typeof value === 'string' ? value.match(/^(20\\d{2})-(\\d{2})-(\\d{2})/) : null\n  if (!match) return null\n  const date = new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3])))\n  if (Number.isNaN(date.getTime())) return null\n  date.setUTCDate(date.getUTCDate() + days)\n  return date.toISOString().slice(0, 10)\n}\n\nexport function outreachWindow(facts, now = Date.now()) {\n  const bid = parsedTime(facts?.bid_deadline)\n  const registration = parsedTime(facts?.registration_deadline)\n  const registrationDate = typeof facts?.registration_deadline_date === 'string'\n    ? facts.registration_deadline_date\n    : null\n  const currentDate = chinaDateKey(now)\n  const registrationDateClosed = Boolean(\n    registrationDate && /^\\d{4}-\\d{2}-\\d{2}$/.test(registrationDate) && registrationDate < currentDate,\n  )\n  if (bid !== null && bid <= now) return { open: false, late: false }\n  if (bid === null && ((registration !== null && registration <= now) || registrationDateClosed)) {\n    return { open: false, late: false }\n  }\n  const late = Boolean(\n    bid !== null && bid > now &&\n    ((registration !== null && registration <= now) || registrationDateClosed),\n  )\n  if (late) return { open: true, late: true }\n\n  if (\n    bid === null &&\n    registration === null &&\n    !registrationDate &&\n    hasRelativeRegistrationWindow(facts)\n  ) {\n    const relativeEndDate = addDaysDateKey(facts?.published_at, 7)\n    if (!relativeEndDate) return { open: false, late: false, relative: true }\n    return { open: currentDate <= relativeEndDate, late: false, relative: true }\n  }\n\n  return { open: true, late: false }\n}\n",
        'outreach-window',
    ),
    (
        'function buildGroundedOutreachDraft(card, privateContext) {\n  const facts = asObject(card?.facts) || {}\n  const marketResearch = isMarketResearch(facts)\n  const window = outreachWindow(facts)\n',
        'export function buildGroundedOutreachDraft(card, privateContext, now = Date.now()) {\n  const facts = asObject(card?.facts) || {}\n  const marketResearch = isMarketResearch(facts)\n  const window = outreachWindow(facts, now)\n',
        'outreach-export-and-clock',
    ),
    (
        "  const budget = normalizeBudget(facts.budget)\n  const factLines = [\n    budget ? `项目预算约${Math.round(budget / 10000)}万元` : null,\n    registration\n      ? `${marketResearch ? '资料提交/报名' : '招标文件获取'}截至${registration}`\n      : registrationDate\n        ? `${marketResearch ? '资料提交/报名' : '招标文件获取'}截止日期为${registrationDate}（官方未公布具体时间）`\n        : null,\n    bid ? `投标/响应截止${bid}` : null,\n  ].filter(Boolean)\n\n  const closing = window.late\n    ? '注意到前期报名或文件获取时间已过，想确认后续是否还有公开答疑或公告允许的资料对接窗口；如无，我们将按公告安排关注后续进展。'\n    : marketResearch\n      ? '想确认目前是否仍接受产品资料、技术交流或需求反馈；如方便，我们可以按公开要求准备相关资料。'\n      : '想确认目前是否还有公开答疑或公告允许的资料对接窗口；如方便，我们可以按项目要求准备相关资料。'\n",
        "  const budget = normalizeBudget(facts.budget)\n  const relativeWindowFact = window.relative\n    ? '官方公告写明测试企业报名期为“自公告发布之日起7天”，未公布精确截止时刻'\n    : null\n  const factLines = [\n    budget ? `项目预算约${Math.round(budget / 10000)}万元` : null,\n    relativeWindowFact,\n    registration\n      ? `${marketResearch ? '资料提交/报名' : '招标文件获取'}截至${registration}`\n      : registrationDate\n        ? `${marketResearch ? '资料提交/报名' : '招标文件获取'}截止日期为${registrationDate}（官方未公布具体时间）`\n        : null,\n    bid ? `投标/响应截止${bid}` : null,\n  ].filter(Boolean)\n\n  const closing = window.relative\n    ? '想确认目前测试企业报名是否仍开放；如仍开放，我们可以按公开要求准备产品资料和技术说明。'\n    : window.late\n      ? '注意到前期报名或文件获取时间已过，想确认后续是否还有公开答疑或公告允许的资料对接窗口；如无，我们将按公告安排关注后续进展。'\n      : marketResearch\n        ? '想确认目前是否仍接受产品资料、技术交流或需求反馈；如方便，我们可以按公开要求准备相关资料。'\n        : '想确认目前是否还有公开答疑或公告允许的资料对接窗口；如方便，我们可以按项目要求准备相关资料。'\n",
        'outreach-relative-copy',
    ),
    (
        "      draft: buildGroundedOutreachDraft(card, privateContext),\n      disclaimer: '发送前请核对公开信息与实际情况；院内关系仅用于内部判断，不会写入外发话术，也不会推断厂家授权或中标概率。',\n",
        "      draft: buildGroundedOutreachDraft(card, privateContext),\n      disclaimer: [\n        '发送前请核对公开信息与实际情况；院内关系仅用于内部判断，不会写入外发话术，也不会推断厂家授权或中标概率。',\n        window.relative ? '公告若仅给相对报名窗口，系统不会把内部推算日期作为官方截止日期。' : null,\n      ].filter(Boolean).join(''),\n",
        'outreach-disclaimer',
    ),
])
