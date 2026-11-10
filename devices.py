from protocol import EthernetFrame, IPPacket, UDPSegment
from config import MAX_SEGMENT_SIZE, TTL_DEFAULT, ETYPE_IPV4, PROTOCOL_UDP, host_a_mac, host_a_ip, host_b_ip, host_b_mac, r1_iface1_ip, r1_iface1_mac, r1_iface2_ip, r1_iface2_mac

### Implements Host, Router, Interface, Route, and SubnetLink classes.
class Host:
    def __init__(self, name, ip, mac, src_port, dst_port):
        self.name = name
        self.ip = ip
        self.mac = mac
        #Links set up at runtime
        self.link = None
        self.src_port = src_port
        self.dst_port = dst_port
        self.mac_table = {}
        self.routing_table = {}
        self.last_ack = None
        self.received_data = []
        self.last_received_seq = None
    #this is called by main, and by hostB when sending back the ack
    def send(self, dst_ip, data):
        if isinstance(data, str):
            data = data.encode()
        
        chunks = [data[i:i + MAX_SEGMENT_SIZE] for i in range(0, len(data), MAX_SEGMENT_SIZE)]
        seq = 0
        for chunk in chunks:
            print(f"{self.name}: Layer 4: Data received from Application Layer. Data size={len(chunk)}")
            self._l4_send(dst_ip, chunk, seq)
            seq ^= 1

    def _l4_send(self, dst_ip, chunk, seq):
        while True:
            self.last_ack = None
            segment = UDPSegment(self.src_port, self.dst_port, UDPSegment.DATA, seq, chunk)
            print(f"{self.name}: Layer 4: Checksum computed")
            print(f"{self.name}: Layer 4: Segment created by adding transport layer header (DATA, seq={seq}) (encapsulation)")
            print(f"{self.name}: Layer 4: Segment sent to Network Layer")
            self._l3_send(dst_ip, segment)
            # ACK arrives synchronously during _l3_send via call stack, so last_ack is set by here
            if self.last_ack == seq:
                print(f"{self.name}: Layer 4: Correct ACK received (seq={seq}), moving on")
                break
            print(f"{self.name}: Layer 4: Wrong/no ACK (got {self.last_ack}, expected {seq}) — retransmitting")
        
    def _l3_send(self, dst_ip, segment):
        packet = IPPacket(self.ip, dst_ip, TTL_DEFAULT, PROTOCOL_UDP, segment)
        print(f"{self.name}: Layer 3: Segment received from Transport Layer: SRC_IP={self.ip}, DST_IP={dst_ip}, TTL={packet.ttl}")
        print(f"{self.name}: Layer 3: Destination IP read: {dst_ip}")

        next_hop = self._route_lookup(dst_ip)
        print(f"{self.name}: Layer 3: Routing table lookup performed")
        print(f"{self.name}: Layer 3: Next-hop IP determined: {next_hop}")
        print(f"{self.name}: Layer 3: Outgoing interface selected")
        print(f"{self.name}: Layer 3: Packet forwarded to Data Link Layer")

        self._l2_send(next_hop, packet)


    def _route_lookup(self, dst_ip):
        for network, next_hop in self.routing_table.items():
            if self._in_network(dst_ip, network):
                if next_hop == "direct":
                    return dst_ip
                return next_hop
        return self.routing_table.get("default")  

    def _in_network(self, ip, network): # Assumes /24 (matches the two-subnet topology). For other prefix lengths, parse the /N.
        if network == "default":
            return False
        net_prefix = network.split("/")[0].rsplit(".", 1)[0]
        ip_prefix = ip.rsplit(".", 1)[0]
        return net_prefix == ip_prefix


    def _l2_send(self, next_hop_ip, packet):
        print(f"{self.name}: Layer 2: Packet received from Network Layer")
        dst_mac = self.mac_table[next_hop_ip]
        print(f"{self.name}: Layer 2: Destination MAC lookup for next-hop IP ({next_hop_ip}) → {dst_mac}")

        frame = EthernetFrame(dst_mac, self.mac, ETYPE_IPV4, packet)
        print(f"{self.name}: Layer 2: Frame created: SRC_MAC={self.mac}, DST_MAC={dst_mac}")
        print(f"{self.name}: Layer 2: Frame sent")

        self.link.transmit(frame)
        
        
    def receive(self, frame):
        self._l2_receive(frame)

    def _l2_receive(self, frame):
        print(f"{self.name}: Layer 2: Frame received")
        if frame.dst_mac != self.mac:
            print(f"{self.name}: Layer 2: Not for me, dropping")
            return
        print(f"{self.name}: Layer 2: Source MAC learned: {frame.src_mac}")
        print(f"{self.name}: Layer 2: Packet delivered to Network Layer")
        self._l3_receive(frame.payload)

    def _l3_receive(self, packet):
        print(f"{self.name}: Layer 3: Packet received from Data Link Layer: SRC_IP={packet.src_ip}, DST_IP={packet.dst_ip}, TTL={packet.ttl}")
        print(f"{self.name}: Layer 3: Destination IP read: {packet.dst_ip}")
        if packet.dst_ip == self.ip:
            print(f"{self.name}: Layer 3: Packet identified as local delivery")
            print(f"{self.name}: Layer 3: Segment delivered to Transport Layer")
            self._l4_receive(packet.payload, packet.src_ip)

    def _l4_receive(self, segment, src_ip):
        print(f"{self.name}: Layer 4: Segment received from Network Layer")

        if not segment.verify_checksum():
            print(f"{self.name}: Layer 4: Segment has been discarded due to failure of checksum")
            if segment.seg_type == UDPSegment.DATA and self.last_received_seq is not None:
                print(f"{self.name}: Layer 4: Re-sending ACK for last good seq={self.last_received_seq}")
                self._send_ack(src_ip, self.last_received_seq)
            return
        print(f"{self.name}: Layer 4: Checksum verified")

        if segment.seg_type == UDPSegment.DATA:
            if segment.seq == self.last_received_seq:
                # Duplicate — don't redeliver, just re-ACK
                print(f"{self.name}: Layer 4: Duplicate seq={segment.seq} — re-sending ACK without delivering")
                self._send_ack(src_ip, self.last_received_seq)
            else:
                print(f"{self.name}: Layer 4: DATA segment delivered to Application Layer. Data size={len(segment.data)}")
                self.received_data.append(segment.data)
                self.last_received_seq = segment.seq
                self._send_ack(src_ip, self.last_received_seq)
        else:  # ACK
            print(f"{self.name}: Layer 4: ACK received: seq={segment.seq}")
            self.last_ack = segment.seq

    def _send_ack(self, dst_ip, seq):
        ack = UDPSegment(self.src_port, self.dst_port, UDPSegment.ACK, seq, b"")
        print(f"{self.name}: Layer 4: Segment created by adding transport layer header (ACK, seq={seq})")
        print(f"{self.name}: Layer 4: Segment sent to Network Layer")

        packet = IPPacket(self.ip, dst_ip, TTL_DEFAULT, PROTOCOL_UDP, ack)
        print(f"{self.name}: Layer 3: Segment received from Transport Layer: SRC_IP={self.ip}, DST_IP={dst_ip}, TTL={packet.ttl}")
        print(f"{self.name}: Layer 3: Destination IP read: {dst_ip}")

        next_hop = self._route_lookup(dst_ip)
        print(f"{self.name}: Layer 3: Routing table lookup performed")
        print(f"{self.name}: Layer 3: Next-hop IP determined: {next_hop}")
        print(f"{self.name}: Layer 3: Outgoing interface selected")
        print(f"{self.name}: Layer 3: Packet forwarded to Data Link Layer")

        self._l2_send(next_hop, packet)


class Router:
    def __init__(self,name):
        self.name = name
        self.interfaces = {}
        self.routing_table = {}
        self.mac_table = {}
        self.link1 = None
        self.link2 = None
    
    def receive_iface1(self, frame):
        self._l2_receive(frame, self.interfaces["i1"])
    
    def receive_iface2(self, frame):
        self._l2_receive(frame, self.interfaces["i2"])

    def _l2_receive(self, frame, in_interface):
        
        if frame.dst_mac != in_interface.mac: #Dropped Frames
            print(f"{self.name}: Layer 2: Frame received on {in_interface.name} not for me, dropping")
            return
        print(f"{self.name}: Layer 2: Frame received on {in_interface.name}")
        print(f"{self.name}: Layer 2: Source MAC learned: {frame.src_mac} on {in_interface.name}")
        print(f"{self.name}: Layer 2: Packet delivered to Network Layer")
        self._l3_receive(frame.payload, in_interface)
 
    def _l3_receive(self, packet, in_interface):
        print(f"{self.name}: Layer 3: Packet received from Data Link Layer: "
              f"SRC_IP={packet.src_ip}, DST_IP={packet.dst_ip}, TTL={packet.ttl}")
        print(f"{self.name}: Layer 3: Destination IP read: {packet.dst_ip}")
 
        new_ttl = packet.ttl - 1
        print(f"{self.name}: Layer 3: TTL decremented: {packet.ttl} → {new_ttl}")
        packet.ttl = new_ttl
        if packet.ttl <= 0:
            print(f"{self.name}: Layer 3: Packet dropped due to TTL expiry")
            return
       
        next_hop, out_interface = self._route_lookup(packet.dst_ip)
        print(f"{self.name}: Layer 3: Routing table lookup performed")
        print(f"{self.name}: Layer 3: Next-hop IP determined: {next_hop}")
        print(f"{self.name}: Layer 3: Outgoing interface selected ({out_interface.name})")
        print(f"{self.name}: Layer 3: Packet forwarded to Data Link Layer")
        self._l2_send(next_hop, out_interface, packet) 

    def _route_lookup(self, dst_ip):
        for network, route in self.routing_table.items():
            if self._in_network(dst_ip, network):
                if route.next_hop == "direct":
                    return dst_ip, route.interface
                return route.next_hop, route.interface
        return None, None

    def _in_network(self, ip, network):
        net_prefix = network.split("/")[0].rsplit(".", 1)[0]
        ip_prefix = ip.rsplit(".", 1)[0]
        return net_prefix == ip_prefix

    def _l2_send(self, next_hop_ip, out_interface, packet):
        print(f"{self.name}: Layer 2: Packet received from Network Layer")
        dst_mac = self.mac_table[next_hop_ip]
        src_mac = out_interface.mac                               # ← Interface object's MAC
        print(f"{self.name}: Layer 2: Destination MAC lookup for next-hop IP ({next_hop_ip}) → {dst_mac}")

        frame = EthernetFrame(dst_mac, src_mac, ETYPE_IPV4, packet)
        print(f"{self.name}: Layer 2: Frame created: SRC_MAC={src_mac}, DST_MAC={dst_mac}")
        print(f"{self.name}: Layer 2: Frame forwarded on {out_interface.name}")

        # Pick which link to transmit on, based on which interface
        if out_interface is self.interfaces["i1"]:
            self.link1.transmit(frame)
        else:
            self.link2.transmit(frame)
        
class Interface:
    def __init__(self, name, ip, mac):
        self.name = name
        self.ip = ip
        self.mac = mac

#routes to interfaces based on next_hop
class Route:
    def __init__(self,next_hop,interface):
        self.next_hop = next_hop
        self.interface = interface


#This class allows nodes to communicate with eachother, like a cable
#connect is used to link a destination mac address with a recieve function, i.e hostA's MAC with their recieve function
#transmit is called by nodes on their links. the frames destination mac is then used as the key in linked_devices, in order to call the correct recieve function
class SubNetLink:
    def __init__(self):
        self.linked_devices = {}
    def connect(self,mac,callback_function):
        self.linked_devices[mac] = callback_function
    def transmit(self, frame):
        dst_mac = frame.dst_mac

        if dst_mac in self.linked_devices:
            self.linked_devices[dst_mac](frame)


def build_topology():
    #the actual setup of the devices

    #hostA, routing table for subnet (router interface1), mac table links interface1 ip to interface1 mac
    hostA = Host("Host A",host_a_ip,host_a_mac,5000,80)
    hostA.routing_table = {
        "10.0.1.0/24": "direct",
        "default":     r1_iface1_ip}

    hostA.mac_table = {
        r1_iface1_ip: r1_iface1_mac
    }
    #similarly for hostB
    hostB = Host("Host B",host_b_ip,host_b_mac,80,5000)
    hostB.routing_table = {
        "10.0.2.0/24": "direct",
        "default": r1_iface2_ip
    }
    hostB.mac_table = {
        r1_iface2_ip: r1_iface2_mac
    }

    #router is its own class, has 2 interfaces, otherwise similar setup to hA and hB
    router = Router("Router R1")
    router.interfaces = {
        "i1": Interface("Interface 1", r1_iface1_ip, r1_iface1_mac),
        "i2": Interface("Interface 2", r1_iface2_ip, r1_iface2_mac),
    }

    router.routing_table = {
        "10.0.1.0/24": Route("direct", router.interfaces["i1"]),
        "10.0.2.0/24": Route("direct", router.interfaces["i2"]),
    }
    router.mac_table = {
        host_a_ip: host_a_mac,
        host_b_ip: host_b_mac,
    }

    #Now that devices are set up we can use subnetlinks to connect them
    link_1 = SubNetLink()
    link_2 = SubNetLink()
    #connects devices to the links, passing their respective receive functions
    link_1.connect(host_a_mac,    hostA.receive)
    link_1.connect(r1_iface1_mac, router.receive_iface1)
    link_2.connect(host_b_mac,    hostB.receive)
    link_2.connect(r1_iface2_mac, router.receive_iface2)
    #then sets the link variables in the objects so that they can call transmit
    hostA.link  = link_1
    hostB.link  = link_2
    router.link1 = link_1
    router.link2 = link_2

    return hostA, hostB, router

