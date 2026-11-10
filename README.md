# Mini Internet Protocol Stack

My fork of the two-person team repo, renamed; the original history is his, the README and the `My part` numbers are mine.

A Python simulation of Ethernet/IP/UDP framing, routing and rdt2.2 reliable delivery across two subnets: `python main.py 1200` sends 1,200 bytes from Host A through Router R1 to Host B as three checksummed segments (500 + 500 + 200 bytes), and all three come back ACKed in a 225-line per-layer log.

University team project, 2026, built with one teammate. Standard library only, no dependencies.

## My part

I wrote the packet classes (`EthernetFrame`, `IPPacket`, `UDPSegment`) and the checksum in `protocol.py`, 116 of its 121 lines, and 102 of the 304 lines in `devices.py`: the rdt2.2 send and retransmit loop in `Host._l4_send`, the host receive path up to the rdt2.2 ACK reply, and 16 lines of `Router`. I also wrote 44 of the 46 lines in the team's original README, and 20 of the team's 34 commits on `main` are mine (my fork commit comes after them, under my noreply address).

The numbers come from running these in this repo. `f7e7c1b` is the team's last commit before my fork commit, which reworded one of my comment lines in `devices.py` and replaced the old README, so the blame runs pin to it:

```sh
git blame -w --line-porcelain f7e7c1b -- protocol.py | grep -c "^author-mail <dennisquek027@gmail.com>"
git blame -w --line-porcelain f7e7c1b -- devices.py | grep -c "^author-mail <dennisquek027@gmail.com>"
git blame -w --line-porcelain f7e7c1b -- Readme.md | grep -c "^author-mail <dennisquek027@gmail.com>"
git log main --author=dennisquek027@gmail.com --oneline | wc -l
git shortlog -sn f7e7c1b
```

(`-w` ignores whitespace-only changes. Without it `devices.py` counts 147 of 304 for me, because a later commenting pass reformatted lines.)

## How to run

Python 3.8 or newer:

```sh
python main.py 100    # one segment
python main.py 1200   # three segments (500, 500, then 200 bytes)
```

The output is a per-layer log of every step, in a fixed word-for-word format so runs can be compared line by line.

## Tests

There's no test suite. The check is the log itself: on 23 Oct 2026 (Python 3.13) `python main.py 1200` exited 0, printed 225 lines and three `Correct ACK received` lines (seq 0, 1, 0), with Host B's checksum verified on every segment.

## How it works

Subnet 1 is `10.0.1.0/24` and subnet 2 is `10.0.2.0/24`. MACs and routing tables are hardcoded in `config.py` and `devices.py`.

| File | Purpose |
|---|---|
| `main.py` | Entry point. Takes the message size from the command line and calls `hostA.send()`. |
| `config.py` | Fixed constants: IPs, MACs, default TTL, max segment size (500). |
| `protocol.py` | Header classes: `EthernetFrame` (L2), `IPPacket` (L3), `UDPSegment` (L4). UDP carries the 16-bit 1's complement checksum and the rdt2.2 seq/ACK fields. |
| `devices.py` | `Host`, `Router`, `Interface`, `Route` and `SubNetLink`, plus the topology setup at the bottom. |

**L4 (transport).** `Host.send()` splits the message into chunks of up to 500 bytes. Each chunk becomes a `UDPSegment` with a sequence number alternating 0/1 and a checksum over ports, length, type, seq and payload. The sender waits for the matching ACK and retransmits the same seq on a wrong or missing one.

**L3 (network).** The segment is wrapped in an `IPPacket` with source/destination IP and TTL 100. Each device looks the destination up in its routing table (a direct route returns the destination IP itself as next hop, otherwise the next hop is the router interface). The router decrements TTL on every packet and drops it at zero.

**L2 (data link).** The packet is wrapped in an `EthernetFrame`. The next-hop IP is mapped to a MAC through the device's MAC table (hardcoded, so it acts as static ARP), and `SubNetLink` delivers the frame to the device whose MAC matches. Frames addressed to anyone else are dropped.

**rdt2.2.** The receiver verifies the checksum, throws away corrupted segments and re-sends the last good ACK. A duplicate seq gets re-ACKed without being delivered twice.

## What broke

- **The checksum carry.** Adding up a few hundred 16-bit words overflows 16 bits by more than one carry's worth, so folding the carry back in once isn't enough. `compute_checksum()` keeps folding (`while total > 0xFFFF`) until it fits, then flips the bits for the 1's complement.
- **The ACK only works because it's synchronous.** The first end-to-end run looped forever. The design that works leans on the whole simulation being one call stack: the ACK travels back up through `_l3_send` before `_l4_send` checks `last_ack`, so there's no thread and no timer. That keeps it simple, but it also means a segment that's dropped every time gets retransmitted forever, since nothing ever times out.

## Status and limits

- Finished, not maintained.
- One fixed topology (two hosts, one router), and route matching assumes /24 networks.
- No timers, no retry cap and no packet-loss injection, see above.
- The TTL-expiry path isn't exercised by the normal run, because every packet starts at TTL 100 and crosses one router.

AI use: this README was drafted with Claude from the team README and the code, then checked by running `main.py`.

No licence: all rights reserved, shared for viewing.
