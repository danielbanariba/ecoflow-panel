# The EcoFlow IoT Developer API, as it actually behaves

Notes from making this work, including where the published documentation and the
live service disagree.

## Endpoint

```
GET https://api.ecoflow.com/iot-open/sign/device/list
GET https://api.ecoflow.com/iot-open/sign/device/quota/all?sn=<serial>
```

Headers on every request:

| Header | Value |
|---|---|
| `accessKey` | your access key |
| `nonce` | six random digits |
| `timestamp` | milliseconds since epoch |
| `sign` | HMAC-SHA256 hex digest, see below |
| `Content-Type` | `application/json` |

## Signing

The documented scheme: flatten and sort the request parameters, join as
`k=v&k=v`, append `accessKey`, `nonce`, `timestamp` in that order, HMAC-SHA256
with the secret key.

Measured against the live service:

| Signed string | Result |
|---|---|
| `sn=<serial>&accessKey=…&nonce=…&timestamp=…` | `8521 signature is wrong` |
| `accessKey=…&nonce=…&timestamp=…` (sn in the URL only) | `0 Success`, 242 fields |

**On GET, the query parameters stay out of the signed string.** `sn` travels in
the URL alone.

`/device/list` takes no parameters, so both forms produce the same string and it
succeeds either way. That is what makes this hard to spot: the first call you
write works, and the failure only appears on the second.

## Fields worth knowing

242 come back. The ones this project uses:

| Field | Meaning |
|---|---|
| `ems.lcdShowSoc` | charge, the same figure the unit prints on its own screen |
| `bmsMaster.soc`, `bmsMaster.actSoc` | BMS charge — sits a percent or two off the display |
| `bmsMaster.f32ShowSoc` | charge with decimals |
| `inv.acInVol` | **AC input, millivolts.** ~115000 with mains present, 0 without |
| `inv.inputWatts` | draw from the wall — also 0 when the pack is full |
| `bmsMaster.inputWatts` / `outputWatts` | charge direction |
| `ems.chgRemainTime` / `ems.dsgRemainTime` | minutes to full / to empty |

`inv.acInVol` is the honest outage signal. `inputWatts` is not: it reads zero
both when the grid is down and when the pack has finished charging, so a
watts-based check fires a false blackout after every charge.

## Rate limits

Not documented. This client caches for 60 seconds and treats a stale reading as
better than a rejected one; the figure moves slowly enough that nothing is lost.

## Keys

From [developer.ecoflow.com](https://developer.ecoflow.com) → *Security
Information Management* → **Create AccessKey**. Account approval is said to take
up to a week; in practice it may already be enabled when you first sign in.

Creating a new key does not revoke the old one. Delete the old one explicitly in
the `operate` column, then confirm: a request with the old key must **fail**. If
it still succeeds, the key is still live.
