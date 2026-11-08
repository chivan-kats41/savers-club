# Account & payout security

## Sign-in rules
- **Unverified phone = no sign-in.** A person whose phone number is not verified cannot sign in, whatever their role
  (member, merchant, rider, agent). The correct password only leads to the verification page; no session exists until the
  texted code is accepted. Registration signs nobody in either. Only two code paths ever create a session
  (`verify_phone` after a good code, `login_view` for verified users and admins) and both are covered by tests.
- **Admins are unchanged**: they can sign in without phone verification, and super admins still receive member, merchant,
  rider and agent profiles automatically (`accounts/admin_profiles.py`, untouched).
- Verification only accepts **registration** codes. A withdrawal or other code can never verify a phone.

## Signing in with a phone number OR an email
- Both work on the main login page (`/accounts/login/`) **and** on `/django-admin/login/`. Phone in any spelling (`0772…`, `+256 772…`),
  email in any letter-case, with stray spaces ignored.
- Everyone can have an email: optional at signup, and **Account** (top bar, `/accounts/account/`) lets anyone add, change or remove
  it after signing up. It needs the current password, the email must not belong to another account, it is stored lower-case, and
  wrong passwords there count toward the normal lockout. An email never replaces the phone: the phone stays verified and
  unverified phones still cannot sign in.
- Fixed: `/django-admin/login/` limited the username to 20 characters (the phone column), so a browser cut long emails short; and it
  recorded no failed attempts. It now takes up to 254 characters and shares the lockout and network-ceiling rules.
- Blank signup emails are stored as NULL, never `""` (the column is unique), and emails are normalised to lower-case.
- Known gap: emails are not yet *verified* (no confirmation mail is sent). Use is limited to signing in to the same account that
  already has a verified phone, so this is low risk, but add email verification before using email for password reset.

## One SIM, one account
Phones are stored as `+2567XXXXXXXX`. Registration accepts `0772…`, `772…`, `+256 772…` etc., rejects anything that isn't a
Ugandan mobile, and treats every spelling as the same number (including accounts created the old way). Login accepts any
spelling. Migration `accounts.0007` rewrites existing numbers **only when exactly one account owns the number**; if two
accounts hold the same SIM under different spellings, both are left for a person to resolve. Find them with:
`python manage.py shell -c "from accounts.models import User; from accounts.phone import canonical_phone as c; import collections; d=collections.defaultdict(list); [d[c(u.phone)].append(u.pk) for u in User.objects.all() if c(u.phone)]; print({k:v for k,v in d.items() if len(v)>1})"`

## Failed-login limits
- Per account: 5 failures in 15 minutes, counted per person (phone spelling and e-mail letter-case no longer give fresh guesses).
- Per network address: 40 failures across ALL accounts in 15 minutes pauses that address (credential stuffing). Generous on purpose:
  many users share one carrier address. Tune with the `security.login_ip_failure_limit` setting (never below 10).
- Known trade-off: anyone can still lock a *specific* person out for 15 minutes by failing five times for them.

## Withdrawals
- Every withdrawal needs a **6-digit code texted to the phone on the account** (never the payout number named in the request).
  Code: hashed, 10-minute life, 5 guesses, 3 issued per hour. It is consumed only when the withdrawal is created, so a rejected
  request (low balance, daily cap) does not burn it.
- **Daily cap**: `withdrawal.daily_limit_ugx` (default UGX 1,000,000) over a rolling 24 h per person, across rider and referral
  money; failed/reversed withdrawals don't count. Choose a number that fits your riders' real earnings.
- `withdrawal.require_code=0` switches the code off (local testing without SMS only). In DEBUG the code is shown on screen.

## Claim codes
A merchant gets 8 wrong or foreign claim codes per 15 minutes; after that redeeming pauses (and a risk event is logged). A good
redemption clears the streak. (The old per-claim attempt counter could never trigger: the first valid attempt redeems the claim.)

## Also
`.dockerignore` keeps `.env`, the database and logs out of Docker images.
