#
# Copyright 2019 Red Hat, Inc.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301 USA
#
# Refer to the README and COPYING files for full details of the license
#

from __future__ import absolute_import
from __future__ import division

import pytest

from vdsm.network import nmstate

from network.compat import mock


IFACE0 = 'eth0'
IFACE1 = 'eth1'

VLAN101 = 101

IPv4_ADDRESS1 = '192.0.2.1'
IPv4_GATEWAY1 = '192.0.2.254'
IPv4_NETMASK1 = '255.255.255.0'
IPv4_PREFIX1 = 24
IPv6_ADDRESS1 = 'fdb3:84e5:4ff4:55e3::1'
IPv6_PREFIX1 = 64

IPv4_ADDRESS2 = '192.0.3.1'
IPv4_NETMASK2 = '255.255.255.0'
IPv4_PREFIX2 = 24
IPv6_ADDRESS2 = 'fdb3:84e5:4ff4:88e3::1'
IPv6_PREFIX2 = 64


parametrize_bridged = pytest.mark.parametrize('bridged', [False, True],
                                              ids=['bridgeless', 'bridged'])


def test_translate_empty_networks_and_bonds():
    state = nmstate.generate_state(networks={}, bondings={})

    assert {nmstate.Interface.KEY: []} == state


@parametrize_bridged
def test_translate_nets_without_ip(bridged):
    networks = {
        'testnet1': _create_network_config('nic', IFACE0, bridged),
        'testnet2': _create_network_config('nic', IFACE1, bridged)
    }
    state = nmstate.generate_state(networks=networks, bondings={})

    eth0_state = _create_ethernet_iface_state(IFACE0)
    eth1_state = _create_ethernet_iface_state(IFACE1)

    _disable_iface_ip(eth0_state, eth1_state)

    expected_state = {
        nmstate.Interface.KEY: [
            eth0_state,
            eth1_state
        ]
    }
    if bridged:
        bridge1_state = _create_bridge_iface_state(
            'testnet1', IFACE0, options=_generate_bridge_options(
                stp_enabled=False)
        )
        bridge2_state = _create_bridge_iface_state(
            'testnet2', IFACE1, options=_generate_bridge_options(
                stp_enabled=False)
        )
        _disable_iface_ip(bridge1_state, bridge2_state)
        expected_state[nmstate.Interface.KEY].extend([
            bridge1_state,
            bridge2_state
        ])
    _sort_by_name(expected_state[nmstate.Interface.KEY])
    assert expected_state == state


@parametrize_bridged
def test_translate_nets_with_ip(bridged):
    networks = {
        'testnet1': _create_network_config(
            'nic', IFACE0, bridged,
            static_ip_configuration=_create_static_ip_configuration(
                IPv4_ADDRESS1, IPv4_NETMASK1, IPv6_ADDRESS1, IPv6_PREFIX1)
        ),
        'testnet2': _create_network_config(
            'nic', IFACE1, bridged,
            static_ip_configuration=_create_static_ip_configuration(
                IPv4_ADDRESS2, IPv4_NETMASK2, IPv6_ADDRESS2, IPv6_PREFIX2)
        )
    }
    state = nmstate.generate_state(networks=networks, bondings={})

    eth0_state = _create_ethernet_iface_state(IFACE0)
    eth1_state = _create_ethernet_iface_state(IFACE1)

    ip0_state = _create_ipv4_state(IPv4_ADDRESS1, IPv4_PREFIX1)
    ip0_state.update(_create_ipv6_state(IPv6_ADDRESS1, IPv6_PREFIX1))
    ip1_state = _create_ipv4_state(IPv4_ADDRESS2, IPv4_PREFIX2)
    ip1_state.update(_create_ipv6_state(IPv6_ADDRESS2, IPv6_PREFIX2))

    expected_state = {nmstate.Interface.KEY: [eth0_state, eth1_state]}
    if bridged:
        _disable_iface_ip(eth0_state, eth1_state)
        bridge1_state = _create_bridge_iface_state(
            'testnet1', IFACE0, options=_generate_bridge_options(
                stp_enabled=False)
        )
        bridge2_state = _create_bridge_iface_state(
            'testnet2', IFACE1, options=_generate_bridge_options(
                stp_enabled=False)
        )
        bridge1_state.update(ip0_state)
        bridge2_state.update(ip1_state)
        expected_state[nmstate.Interface.KEY].extend([
            bridge1_state,
            bridge2_state
        ])
    else:
        eth0_state.update(ip0_state)
        eth1_state.update(ip1_state)

    _sort_by_name(expected_state[nmstate.Interface.KEY])
    assert expected_state == state


def test_translate_new_bond_with_two_slaves():
    bondings = {
        'testbond0': {
            'nics': [IFACE0, IFACE1],
            'switch': 'legacy'
        }
    }
    state = nmstate.generate_state(networks={}, bondings=bondings)

    bond0_state = _create_bond_iface_state(
        'testbond0', 'balance-rr', [IFACE0, IFACE1])

    _disable_iface_ip(bond0_state)

    expected_state = {
        nmstate.Interface.KEY: [
            bond0_state,
        ]
    }
    assert expected_state == state


@mock.patch.object(nmstate, 'RunningConfig')
def test_translate_edit_bond_with_slaves(rconfig_mock):
    bondings = {
        'testbond0': {
            'nics': [IFACE0, IFACE1],
            'switch': 'legacy'
        }
    }
    rconfig_mock.return_value.bonds = bondings

    state = nmstate.generate_state(networks={}, bondings=bondings)

    bond0_state = _create_bond_iface_state(
        'testbond0', 'balance-rr', [IFACE0, IFACE1])

    expected_state = {
        nmstate.Interface.KEY: [
            bond0_state,
        ]
    }
    assert expected_state == state


def test_translate_new_bond_with_two_slaves_and_options():
    bondings = {
        'testbond0': {
            'nics': [IFACE0, IFACE1],
            'options': 'mode=4 miimon=150',
            'switch': 'legacy'
        }
    }
    state = nmstate.generate_state(networks={}, bondings=bondings)

    bond0_state = _create_bond_iface_state(
        'testbond0', '802.3ad', [IFACE0, IFACE1], miimon='150')

    _disable_iface_ip(bond0_state)

    expected_state = {
        nmstate.Interface.KEY: [
            bond0_state,
        ]
    }
    assert expected_state == state


@parametrize_bridged
def test_translate_net_with_ip_on_bond(bridged):
    networks = {
        'testnet1': _create_network_config(
            'bonding', 'testbond0', bridged,
            static_ip_configuration=_create_static_ip_configuration(
                IPv4_ADDRESS1, IPv4_NETMASK1, IPv6_ADDRESS1, IPv6_PREFIX1))
    }
    bondings = {
        'testbond0': {
            'nics': [IFACE0, IFACE1],
            'switch': 'legacy'
        }
    }
    state = nmstate.generate_state(networks=networks, bondings=bondings)

    bond0_state = _create_bond_iface_state(
        'testbond0', 'balance-rr', [IFACE0, IFACE1])

    ip_state = _create_ipv4_state(IPv4_ADDRESS1, IPv4_PREFIX1)
    ip_state.update(_create_ipv6_state(IPv6_ADDRESS1, IPv6_PREFIX1))

    expected_state = {nmstate.Interface.KEY: [bond0_state]}
    if bridged:
        _disable_iface_ip(bond0_state)
        bridge1_state = _create_bridge_iface_state(
            'testnet1', 'testbond0', options=_generate_bridge_options(
                stp_enabled=False)
        )
        bridge1_state.update(ip_state)
        expected_state[nmstate.Interface.KEY].extend([bridge1_state])
    else:
        bond0_state.update(ip_state)

    assert expected_state == state


@parametrize_bridged
def test_translate_net_with_dynamic_ip(bridged):
    networks = {
        'testnet1': _create_network_config(
            'bonding', 'testbond0', bridged,
            dynamic_ip_configuration=_create_dynamic_ip_configuration(
                dhcpv4=True, dhcpv6=True, ipv6autoconf=True))
    }
    bondings = {
        'testbond0': {
            'nics': [IFACE0, IFACE1],
            'switch': 'legacy'
        }
    }
    state = nmstate.generate_state(networks=networks, bondings=bondings)

    bond0_state = _create_bond_iface_state(
        'testbond0', 'balance-rr', [IFACE0, IFACE1])

    ip_state = _create_ipv4_state(dynamic=True)
    ip_state.update(_create_ipv6_state(dynamic=True))

    expected_state = {nmstate.Interface.KEY: [bond0_state]}
    if bridged:
        _disable_iface_ip(bond0_state)
        bridge1_state = _create_bridge_iface_state(
            'testnet1', 'testbond0', options=_generate_bridge_options(
                stp_enabled=False)
        )
        bridge1_state.update(ip_state)
        expected_state[nmstate.Interface.KEY].extend([bridge1_state])
    else:
        bond0_state.update(ip_state)

    assert expected_state == state


@parametrize_bridged
def test_translate_net_with_ip_on_vlan_on_bond(bridged):
    networks = {
        'testnet1': _create_network_config(
            'bonding', 'testbond0', bridged,
            static_ip_configuration=_create_static_ip_configuration(
                IPv4_ADDRESS1, IPv4_NETMASK1, IPv6_ADDRESS1, IPv6_PREFIX1),
            vlan=VLAN101)
    }
    bondings = {
        'testbond0': {
            'nics': [IFACE0, IFACE1],
            'switch': 'legacy'
        }
    }
    state = nmstate.generate_state(networks=networks, bondings=bondings)

    bond0_state = _create_bond_iface_state(
        'testbond0', 'balance-rr', [IFACE0, IFACE1])

    _disable_iface_ip(bond0_state)

    vlan101_state = _create_vlan_iface_state('testbond0', VLAN101)
    ip1_state = _create_ipv4_state(IPv4_ADDRESS1, IPv4_PREFIX1)
    ip1_state.update(_create_ipv6_state(IPv6_ADDRESS1, IPv6_PREFIX1))

    expected_state = {nmstate.Interface.KEY: [bond0_state, vlan101_state]}
    if bridged:
        _disable_iface_ip(vlan101_state)
        bridge1_state = _create_bridge_iface_state(
            'testnet1',
            vlan101_state['name'],
            options=_generate_bridge_options(stp_enabled=False)
        )
        bridge1_state.update(ip1_state)
        expected_state[nmstate.Interface.KEY].extend([bridge1_state])
    else:
        vlan101_state.update(ip1_state)
    assert expected_state == state


@parametrize_bridged
@mock.patch.object(nmstate, 'RunningConfig')
def test_translate_remove_nets(rconfig_mock, bridged):
    rconfig_mock.return_value.networks = {
        'testnet1': {
            'nic': IFACE0, 'bridged': bridged, 'switch': 'legacy',
            'defaultRoute': False},
        'testnet2': {
            'nic': IFACE1, 'bridged': bridged, 'switch': 'legacy',
            'defaultRoute': False}
    }
    networks = {
        'testnet1': {'remove': True},
        'testnet2': {'remove': True}
    }
    state = nmstate.generate_state(networks=networks, bondings={})

    eth0_state = _create_ethernet_iface_state(IFACE0)
    eth1_state = _create_ethernet_iface_state(IFACE1)

    _disable_iface_ip(eth0_state, eth1_state)

    expected_state = {nmstate.Interface.KEY: [eth0_state, eth1_state]}
    if bridged:
        expected_state[nmstate.Interface.KEY].extend([
            {
                'name': 'testnet1',
                'state': 'absent'
            },
            {
                'name': 'testnet2',
                'state': 'absent'
            }
        ])
    _sort_by_name(expected_state[nmstate.Interface.KEY])
    assert expected_state == state


@parametrize_bridged
@mock.patch.object(nmstate, 'RunningConfig')
def test_translate_remove_vlan_net(rconfig_mock, bridged):
    rconfig_mock.return_value.networks = {
        'testnet1': {
            'nic': IFACE0,
            'bridged': bridged,
            'vlan': VLAN101,
            'switch': 'legacy',
            'defaultRoute': False
        }
    }
    networks = {
        'testnet1': {'remove': True}
    }
    state = nmstate.generate_state(networks=networks, bondings={})

    expected_state = {
        nmstate.Interface.KEY: [
            {
                'name': IFACE0 + '.' + str(VLAN101),
                'state': 'absent',
            }
        ]
    }
    if bridged:
        expected_state[nmstate.Interface.KEY].append({
            'name': 'testnet1',
            'state': 'absent'
        })
    _sort_by_name(expected_state[nmstate.Interface.KEY])
    assert expected_state == state


def test_translate_remove_bonds():
    bondings = {
        'testbond0': {'remove': True}
    }

    state = nmstate.generate_state(networks={}, bondings=bondings)

    expected_state = {
        nmstate.Interface.KEY: [
            {
                'name': 'testbond0',
                'type': 'bond',
                'state': 'absent',
            }
        ]
    }
    assert expected_state == state


@parametrize_bridged
@mock.patch.object(nmstate, 'RunningConfig')
def test_translate_remove_net_on_bond(rconfig_mock, bridged):
    rconfig_mock.return_value.networks = {
        'testnet1':
            {'bonding': 'testbond0', 'bridged': bridged, 'switch': 'legacy',
             'defaultRoute': False}
    }
    networks = {
        'testnet1': {'remove': True}
    }
    state = nmstate.generate_state(networks=networks, bondings={})

    expected_state = {
        nmstate.Interface.KEY: [
            {
                'name': 'testbond0',
                'state': 'up',
                'ipv4': {'enabled': False},
                'ipv6': {'enabled': False}
            }
        ]
    }
    if bridged:
        expected_state[nmstate.Interface.KEY].append({
            'name': 'testnet1',
            'state': 'absent'
        })
    _sort_by_name(expected_state[nmstate.Interface.KEY])
    assert expected_state == state


@parametrize_bridged
@mock.patch.object(nmstate, 'RunningConfig')
def test_translate_remove_vlan_net_on_bond(rconfig_mock, bridged):
    rconfig_mock.return_value.networks = {
        'testnet1':
            {
                'bonding': 'testbond0',
                'bridged': bridged,
                'vlan': VLAN101,
                'switch': 'legacy',
                'defaultRoute': False
            }
    }
    networks = {
        'testnet1': {'remove': True}
    }
    state = nmstate.generate_state(networks=networks, bondings={})

    expected_state = {
        nmstate.Interface.KEY: [
            {
                'name': 'testbond0.' + str(VLAN101),
                'state': 'absent',
            }
        ]
    }
    if bridged:
        expected_state[nmstate.Interface.KEY].extend([
            {
                'name': 'testnet1',
                'state': 'absent'
            }
        ])
    _sort_by_name(expected_state[nmstate.Interface.KEY])
    assert expected_state == state


@parametrize_bridged
def test_translate_add_network_with_default_route(bridged):
    networks = {
        'testnet1': _create_network_config(
            'nic', IFACE0, bridged=bridged,
            static_ip_configuration=_create_static_ip_configuration(
                IPv4_ADDRESS1, IPv4_NETMASK1, IPv6_ADDRESS1, IPv6_PREFIX1
            ), default_route=True, gateway=IPv4_GATEWAY1
        )
    }
    state = nmstate.generate_state(networks=networks, bondings={})

    eth0_state = _create_ethernet_iface_state(IFACE0)
    ip0_state = _create_ipv4_state(IPv4_ADDRESS1, IPv4_PREFIX1)
    ip0_state.update(_create_ipv6_state(IPv6_ADDRESS1, IPv6_PREFIX1))

    expected_state = {nmstate.Interface.KEY: [eth0_state]}

    if bridged:
        _disable_iface_ip(eth0_state)
        bridge1_state = _create_bridge_iface_state(
            'testnet1', IFACE0, options=_generate_bridge_options(
                stp_enabled=False)
        )
        bridge1_state.update(ip0_state)
        expected_state[nmstate.Interface.KEY].append(bridge1_state)
        if_with_default_route = 'testnet1'
    else:
        eth0_state.update(ip0_state)
        if_with_default_route = IFACE0

    expected_state[nmstate.Route.KEY] = _get_routes_config(
        IPv4_GATEWAY1, if_with_default_route
    )
    assert state == expected_state


@parametrize_bridged
@mock.patch.object(nmstate, 'RunningConfig')
def test_translate_remove_network_with_default_route(rconfig_mock, bridged):
    rconfig_mock.return_value.networks = {
        'testnet1':
            {
                'nic': IFACE0,
                'bridged': bridged,
                'switch': 'legacy',
                'defaultRoute': True,
                'gateway': IPv4_GATEWAY1
            }
    }
    networks = {'testnet1': {'remove': True}}
    state = nmstate.generate_state(networks=networks, bondings={})

    eth0_state = _create_ethernet_iface_state(IFACE0)
    _disable_iface_ip(eth0_state)

    expected_state = {nmstate.Interface.KEY: [eth0_state]}

    if bridged:
        expected_state[nmstate.Interface.KEY].append(
            {'name': 'testnet1', 'state': 'absent'}
        )

    assert expected_state == state


def _sort_by_name(ifaces_states):
    ifaces_states.sort(key=lambda d: d['name'])


def _create_ethernet_iface_state(name):
    return {'name': name, 'state': 'up'}


def _create_bond_iface_state(name, mode, slaves, **options):
    state = {
        'name': name,
        'type': 'bond',
        'state': 'up',
        'link-aggregation': {'mode': mode, 'slaves': slaves}
    }
    if options:
        state['link-aggregation']['options'] = options
    return state


def _create_bridge_iface_state(name, port, options=None):
    bridge_state = {
        'name': name,
        'type': 'linux-bridge',
        'state': 'up',
        'bridge': {
            'port': [
                {
                    'name': port,
                }
            ]
        }
    }
    if options:
        bridge_state['bridge']['options'] = options
    return bridge_state


def _generate_bridge_options(stp_enabled):
    return {
        'stp': {
            'enabled': stp_enabled,
        }
    }


def _create_vlan_iface_state(base, vlan):
    return {
        'name': base + '.' + str(vlan),
        'type': 'vlan',
        'state': 'up',
        'vlan': {'id': vlan, 'base-iface': base}
    }


def _disable_iface_ip(*ifaces_states):
    ip_disabled_state = _create_ipv4_state()
    ip_disabled_state.update(_create_ipv6_state())
    for iface_state in ifaces_states:
        iface_state.update(ip_disabled_state)


def _create_ipv4_state(address=None, prefix=None, dynamic=False):
    state = {'ipv4': {'enabled': False}}
    if dynamic:
        state['ipv4'] = {'enabled': True, 'dhcp': True}
    elif address and prefix:
        state['ipv4'] = {
            'enabled': True,
            'address': [
                {'ip': address, 'prefix-length': prefix}
            ]
        }
    return state


def _create_ipv6_state(address=None, prefix=None, dynamic=False):
    state = {'ipv6': {'enabled': False}}
    if dynamic:
        state['ipv6'] = {'enabled': True, 'dhcp': True, 'autoconf': True}
    elif address and prefix:
        state['ipv6'] = {
            'enabled': True,
            'address': [
                {'ip': address, 'prefix-length': prefix}
            ]
        }
    return state


def _get_routes_config(gateway, next_hop, state=None):
    return {
        nmstate.Route.CONFIG: [_create_default_route(gateway, next_hop, state)]
    }


def _create_default_route(gateway, next_hop, state=None):
    route_state = {
        nmstate.Route.DESTINATION: '0.0.0.0/0',
        nmstate.Route.NEXT_HOP_ADDRESS: gateway,
        nmstate.Route.NEXT_HOP_INTERFACE: next_hop,
        nmstate.Route.TABLE_ID: nmstate.Route.USE_DEFAULT_ROUTE_TABLE
    }
    if state:
        route_state[nmstate.Route.STATE] = state
    return route_state


def _create_network_config(if_type, if_name, bridged,
                           static_ip_configuration=None,
                           dynamic_ip_configuration=None,
                           vlan=None, default_route=False, gateway=None):
    network_config = _create_interface_network_config(if_type, if_name)
    network_config.update(
        _create_bridge_network_config(bridged, stp_enabled=False))
    network_config.update(static_ip_configuration or {})
    network_config.update(dynamic_ip_configuration or {})
    network_config.update({'vlan': vlan} if vlan else {})
    network_config.update({'defaultRoute': default_route})
    network_config.update({'gateway': gateway} if gateway else {})
    return network_config


def _create_interface_network_config(if_type, if_name):
    return {if_type: if_name, 'switch': 'legacy'}


def _create_bridge_network_config(bridged, stp_enabled):
    network_config = {'bridged': bridged}
    if bridged:
        network_config['stp'] = stp_enabled
    return network_config


def _create_static_ip_configuration(ipv4_address, ipv4_netmask, ipv6_address,
                                    ipv6_prefix_length):
    ip_config = {}
    if ipv4_address and ipv4_netmask:
        ip_config['ipaddr'] = ipv4_address
        ip_config['netmask'] = ipv4_netmask
    if ipv6_address and ipv6_prefix_length:
        ip_config['ipv6addr'] = ipv6_address + '/' + str(ipv6_prefix_length)
    return ip_config


def _create_dynamic_ip_configuration(dhcpv4, dhcpv6, ipv6autoconf):
    dynamic_ip_config = {}
    if dhcpv4:
        dynamic_ip_config['bootproto'] = 'dhcp'
    if dhcpv6:
        dynamic_ip_config['dhcpv6'] = True
    if ipv6autoconf:
        dynamic_ip_config['ipv6autoconf'] = True
    return dynamic_ip_config
