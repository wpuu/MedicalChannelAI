# Mobile acceptance checklist

This checklist is for real-device testing of the public trial on `medicalai.qd.je`.

## Required widths

- 360 px Android/WeChat-like viewport
- 390 px iPhone-like viewport
- 430 px large phone viewport

## Header and navigation

- Product title is visible and does not collide with controls.
- No trial-mode pill sits beside the active page tab on phone.
- Main phone navigation is fixed at the bottom and exposes 今日、商机、跟进、资源.
- Bottom navigation respects safe-area inset and does not cover page actions.
- Build/version label is not visible on phone.

## Copy

- No raw lifecycle enum such as `BIDDING`, `OPEN`, `PARTIAL`, `VERIFIED` appears in user-facing UI.
- Bidding projects display “招标中”.
- No “Pilot” wording appears in the main phone experience.
- Internal implementation labels such as “AI任务队列” are not presented as user metrics.

## AI controls

- Start AI analysis on one card.
- Every other AI generation button becomes disabled immediately.
- The active card shows “AI分析中”.
- Other cards show “已有AI任务处理中”.
- After success/failure, all eligible AI buttons become available again.

## Content

- The first card title, score, stage, budget and deadline fit without horizontal scrolling.
- “查看全部” is reachable without overlapping the coverage note.
- Today metrics remain readable in a 2×2 grid.
- Opening a detail and returning does not lose follow-up state on the same device.

A real-device screenshot is required after deployment because static build checks cannot prove visual rendering in external mobile browser containers.
