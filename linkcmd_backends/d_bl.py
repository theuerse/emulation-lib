from . import backend
from . import commons

class D_BL(backend.Backend):
    # returns the commands to setup common interface-properties indifferent of the number of connections
    # returns commands for the local node only
    def get_common_setup_commands(self, config):
       return commons.get_common_IFBsetup_commands(config)


    # returns setup-commands specific for a connection to a remote ip
    # returns only commands for the local node
    def get_indiv_setup_commands(self, config, mapping, line, local_id, remote_id):
        local_ip = self.getEmuIpFromId(local_id, config)
        local_hostByte = self.getHostByteFromId(local_id, config)
        remote_ip = self.getEmuIpFromId(remote_id, config)
        remote_hostByte = self.getHostByteFromId(remote_id, config)
        local_setup_cmds = []
        remote_setup_cmds = []

        # allow connection from local-ip to remote-ip in simulation-/emulation-network
        local_setup_cmds.append("sudo iptables -A INPUT -d " + local_ip + " -s " + remote_ip + " -j ACCEPT")
        local_setup_cmds.append("sudo iptables -A OUTPUT -d " + remote_ip + " -s " + local_ip + " -j ACCEPT")

        # get target-parameters
        parts = line.split()
        target_bitrate = int(round(float(parts[mapping["rate"]]), 0))

        # allow for different kinds of loss (loss random, loss gemodel, loss state)
        loss_kind = ""
        for key in mapping:
            if key.startswith("loss"):
                loss_kind = key
                target_loss = float(parts[mapping[key]])
                break

        # delay in fraction of a second -> *1000 -> delay in ms
        target_delay = max(0, round((float(parts[mapping["delay"]]) - config["PHYS_LINK_DELAY_COMPENSATION"]) * 1000, 1))

        # catch case of no connectivity at beginning/setup (be able to build tc-command structure, even if bitrate=0 -> normally error)
        if target_bitrate == 0:
            target_bitrate = 1000  # set default bitrate to be 1 Mbit/s (only happens if loss is 100% and bitrate does not matter therefore)

        #
        # local setup (part)
        #
        # add class
        flowId1 = "1:" + remote_hostByte  # towards receiver
        local_setup_cmds.append("sudo tc class add dev " + config[
            "EMU_INTERFACE"] + " parent 1: classid " + flowId1 + " htb rate 100mbit")

        # add filter
        local_setup_cmds.append("sudo tc filter add dev " + config["EMU_INTERFACE"] +
                                " protocol ip parent 1:0 prio 1 u32 match ip dst " + remote_ip +
                                " match ip src " + local_ip + " flowid " + flowId1)

        # add netem-qdisc (delay)
        local_setup_cmds.append("sudo tc qdisc add dev " + config["EMU_INTERFACE"] + " parent " + flowId1 +
                                " handle " + remote_hostByte + ": netem delay " + str(target_delay) + "ms")

        #
        # remote setup (part)
        #
        # add class
        flowId2 = "2:" + local_hostByte  # from sender
        remote_setup_cmds.append("sudo tc class add dev ifb0 parent 2: classid " + flowId2 + " htb rate 100mbit")

        # add filter
        remote_setup_cmds.append("sudo tc filter add dev ifb0" +
                                 " protocol ip parent 2:0 prio 1 u32 match ip dst " + remote_ip +
                                 " match ip src " + local_ip + " flowid " + flowId2)

        # add tbf (limit incoming bitrate)
        burst = self.calculate_TBF_burstsize(target_bitrate, config["PI_CONFIG_HZ"], config["LINK_MTU"])

        remote_setup_cmds.append("sudo tc qdisc add dev ifb0 parent " + flowId2 + " handle " + str(10 * int(local_hostByte)) +
                                 ": tbf rate " + str(target_bitrate) + "kbit burst " + str(burst) + " latency " + str(
            config["LATENCY"]) + "ms" +
                                 " peakrate " + str(target_bitrate + 1) + "kbit mtu " + str(config["LINK_MTU"]))

        # add netem-qdisc (loss)
        remote_setup_cmds.append("sudo tc qdisc add dev ifb0 parent " + str(10 * int(local_hostByte)) + ":" +
                                 " handle " + str(10 * int(local_hostByte) + 1) + ": netem " + loss_kind + " " + str(
            target_loss) + " limit 1")

        return local_setup_cmds, remote_setup_cmds


    # returns commands to change link properties over time
    # returns only commands for the local node
    def get_indiv_change_commands(self, config, mapping, line, local_id, remote_id):
        local_change_cmds = []
        remote_change_cmds = []
        local_hostByte = self.getHostByteFromId(local_id, config)
        remote_hostByte = self.getHostByteFromId(remote_id, config)

        # get target-parameters
        parts = line.split()
        target_bitrate = int(round(float(parts[mapping["rate"]]), 0))

        # allow for different kinds of loss (loss random, loss gemodel, loss state)
        loss_kind = ""
        for key in mapping:
            if key.startswith("loss"):
                loss_kind = key
                target_loss = float(parts[mapping[key]])
                break

        # delay in fraction of a second -> *1000 -> delay in ms
        target_delay = max(0, round((float(parts[mapping["delay"]]) - config["PHYS_LINK_DELAY_COMPENSATION"]) * 1000, 1))

        #
        # local change (part)
        #
        # change netem-qdisc (delay)
        flowId1 = "1:" + remote_hostByte  # towards receiver
        local_change_cmds.append("qdisc change dev " + config["EMU_INTERFACE"] + " parent " + flowId1 +
                                 " handle " + remote_hostByte + ": netem delay " + str(target_delay) + "ms")

        #
        # remote change (part)
        #
        # add class
        flowId2 = "2:" + local_hostByte  # from sender

        # add tbf (limit incoming bitrate)
        burst = self.calculate_TBF_burstsize(target_bitrate, config["PI_CONFIG_HZ"], config["LINK_MTU"])

        remote_change_cmds.append("qdisc change dev ifb0 parent " + flowId2 + " handle " + str(10 * int(local_hostByte)) +
                                  ": tbf rate " + str(target_bitrate) + "kbit burst " + str(burst) + " latency " + str(
            config["LATENCY"]) + "ms" +
                                  " peakrate " + str(target_bitrate + 1) + "kbit mtu " + str(config["LINK_MTU"]))

        # add netem-qdisc (loss)
        remote_change_cmds.append("qdisc change dev ifb0 parent " + str(10 * int(local_hostByte)) + ":" +
                                  " handle " + str(10 * int(local_hostByte) + 1) + ": netem " + loss_kind + " " + str(
            target_loss) + " limit 1")

        return local_change_cmds, remote_change_cmds