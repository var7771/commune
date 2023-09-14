
import torch
import scalecodec
from retry import retry
from typing import List, Dict, Union, Optional, Tuple
from substrateinterface import SubstrateInterface
import commune as c
from typing import List, Dict, Union, Optional, Tuple
from commune.utils.network import ip_to_int, int_to_ip
from rich.prompt import Confirm
from commune.modules.subspace.balance import Balance
from commune.modules.subspace.utils import (U16_NORMALIZED_FLOAT,
                                    U64_MAX,
                                    NANOPERTOKEN, 
                                    U16_MAX, 
                                    is_valid_address_or_public_key, 
                                    )
from commune.modules.subspace.chain_data import (ModuleInfo, custom_rpc_type_registry)

import streamlit as st
import json
from loguru import logger
import os
logger = logger.opt(colors=True)



class Subspace(c.Module):
    """
    Handles interactions with the subspace chain.
    """
    fmt = 'j'
    whitelist = []
    chain_name = 'subspace'
    default_config = c.get_config(chain_name, to_munch=False)
    token_decimals = default_config['token_decimals']
    network = default_config['network']
    chain = network
    chain_path =  f"{c.repo_path}/subspace"
    spec_path = f"{chain_path}/specs"
    netuid = default_config['netuid']
    mode = default_config['mode']
    
    def __init__( 
        self, 
        config = None,
        **kwargs,
    ):

        config = self.set_config(config=config,kwargs=kwargs)
        if config.loop:
            c.thread(self.loop)

    def set_network(self, 
                network:str = None,
                url : str = None,
                websocket:str=None, 
                ss58_format:int=42, 
                type_registry:dict=custom_rpc_type_registry, 
                type_registry_preset=None, 
                cache_region=None, 
                runtime_config=None, 
                use_remote_preset=False,
                ws_options=None, 
                auto_discover=True, 
                auto_reconnect=True, 
                verbose:bool=False,
                *args, 
                **kwargs):

        '''
        A specialized class in interfacing with a Substrate node.

        Parameters
       A specialized class in interfacing with a Substrate node.

        Parameters
        url : the URL to the substrate node, either in format <https://127.0.0.1:9933> or wss://127.0.0.1:9944
        
        ss58_format : The address type which account IDs will be SS58-encoded to Substrate addresses. Defaults to 42, for Kusama the address type is 2
        
        type_registry : A dict containing the custom type registry in format: {'types': {'customType': 'u32'},..}
        
        type_registry_preset : The name of the predefined type registry shipped with the SCALE-codec, e.g. kusama
        
        cache_region : a Dogpile cache region as a central store for the metadata cache
        
        use_remote_preset : When True preset is downloaded from Github master, otherwise use files from local installed scalecodec package
        
        ws_options : dict of options to pass to the websocket-client create_connection function
        : dict of options to pass to the websocket-client create_connection function
                
        '''

        from substrateinterface import SubstrateInterface
        
        if network == None:
            network = self.config.network
        self.network = network
        
        url = c.choice(self.urls(network=network))

        if not url.startswith('ws://'):
            url = 'ws://' + url

    
        self.url = url
        

        self.substrate= SubstrateInterface(
                                    url=url, 
                                    websocket=websocket, 
                                    ss58_format=ss58_format, 
                                    type_registry=type_registry, 
                                    type_registry_preset=type_registry_preset, 
                                    cache_region=cache_region, 
                                    runtime_config=runtime_config, 
                                    ws_options=ws_options, 
                                    auto_discover=auto_discover, 
                                    auto_reconnect=auto_reconnect, 
                                    *args,
                                    **kwargs)
        c.print(f'Connected to {network}: {url}...')
        
    def __repr__(self) -> str:
        return f'<Subspace: network={self.network}>'
    def __str__(self) -> str:
        return f'<Subspace: network={self.network}>'
    
    

    def verify(self, 
               auth,
               max_staleness=100,
               ensure_registered=True,):
        key = c.module('key')(ss58_address=auth['address'])
        verified =  key.verify(auth['data'], bytes.fromhex(auth['signature']), bytes.fromhex(auth['public_key']))
        if not verified:
            return {'verified': False, 'error': 'Signature is invalid.'}
        if auth['address'] != key.ss58_address:
            return {'verified': False, 'error': 'Signature address does not match.'}
        
        data = c.jload(auth['data'])
        
        if data['timestamp'] < c.time() - max_staleness:
            return {'verified': False, 'error': 'Signature is stale.', 'timestamp': data['timestamp'], 'now': c.time()}
        if not self.is_registered(key,netuid= data['netuid']) and ensure_registered:
            return {'verified': False, 'error': 'Key is not registered.'}
        return {'verified': True, 'error': None}
    
    @classmethod
    def cj(cls, *args, remote = True, sleep_interval:str = 100, **kwargs):
        if remote:
            c.print('Remote voting...')
            kwargs['remote'] = False
            return cls.remote_fn('cj', args=args, kwargs=kwargs)
        self = cls()
        while True:
            c.print(f'Sleeping for {sleep_interval} seconds...')
            c.print('Voting...')
            c.sleep(sleep_interval)
            self.vote_pool(*args, **kwargs)

    def key2stake(self,netuid = None, network = None, fmt=fmt,  decimals=2):
        stakes = {m['key']: c.round_decimals(m['stake'], decimals=decimals) \
                     for m in self.my_modules(netuid=netuid, network=network, fmt=fmt)}
        key2address = c.key2address()
        key2stake = {}
        for key_name, address in key2address.items():
            if address in stakes:
                key2stake[key_name]= c.round_decimals(stakes[address], decimals=decimals)

        return key2stake

    def key2staketo(self,netuid = None, network = None, fmt=fmt,  decimals=2):
        staketo = self.stake_to(netuid=netuid, network=network, fmt=fmt)
        my_keys = self.my_keys()
        return key2stake
    def key2balance(self, network = None, fmt=fmt, decimals=2):
        network = self.resolve_network(network)
        
        key2address  = c.key2address()
        balances = self.balances(network=network, fmt=fmt)
        key2balance = {}
        
        for key_name, address in key2address.items():
            if address in balances:
                key2balance[key_name]= c.round_decimals(balances[address], decimals=decimals)
        return key2balance

    def key2tokens(self, network = None, fmt=fmt, decimals=2):
        key2tokens = {}
        key2balance = self.key2balance(network=network, fmt=fmt, decimals=decimals)
        for key, balance in key2balance.items():
            if key not in key2tokens:
                key2tokens[key] = 0
            key2tokens[key] += balance
            
        for netuid in self.netuids():
            key2stake = self.key2stake(network=network, fmt=fmt, netuid=netuid, decimals=decimals)

            for key, stake in key2stake.items():
                if key not in key2tokens:
                    key2tokens[key] = 0
                key2tokens[key] += stake
            
        return key2tokens

    def network_balance(self, network = None, fmt=fmt, update=False):
        state_dict = self.state_dict(network=network, update=update)
        total_balance = 0
        for key, value in state_dict['balances'].items():
            total_balance += value
        return self.format_amount(total_balance, fmt=fmt)

    def network_stake(self, network = None, fmt=fmt, update=False):
        state_dict = self.state_dict(network=network, update=update)
        total_stake = 0
        for modules in state_dict['modules']:
            for module in modules:
                total_stake += module['stake']
        return self.format_amount(total_stake, fmt=fmt)
    
    def market_cap(self, network = network, fmt:str='j', decimals:int=2, update=False):

        total_balance = self.network_balance(network=network, fmt=fmt, update=update)
        total_stake = self.network_stake(network=network, fmt=fmt, update=False) # update=False because we already updated above if needed.
        return c.round_decimals(total_balance + total_stake, decimals=decimals) # update=False because we already updated above if needed.
    mcap = market_cap
    

    def my_tokens(self, network = None,fmt=fmt, decimals=2):
        return sum(self.key2tokens(network=network, fmt=fmt, decimals=decimals).values())

    key2value = key2tokens
    my_value = my_tokens
    networth = my_tokens
    
    def my_stake(self, network = None, netuid=None, fmt=fmt, decimals=2):
        return sum(self.key2stake(network=network, netuid=netuid, fmt=fmt, decimals=decimals).values())
    def my_balance(self, network = None, fmt=fmt, decimals=2):
        return sum(self.key2balance(network=network, fmt=fmt, decimals=decimals).values())
    #####################
    #### Set Weights ####
    #####################
    @retry(delay=0, tries=4, backoff=0, max_delay=0)
    def vote(
        self,
        key: 'c.key' = None,
        uids: Union[torch.LongTensor, list] = None,
        weights: Union[torch.FloatTensor, list] = None,
        netuid: int = None,
        wait_for_inclusion:bool = True,
        wait_for_finalization:bool = True,
        network = None,
    ) -> bool:
        network = self.resolve_network(network)
        key = self.resolve_key(key)
        netuid = self.resolve_netuid(netuid)
        if uids is None:
            uids = self.uids()
        
        subnet = self.subnet( netuid = netuid )
        min_allowed_weights = subnet['min_allowed_weights']
        max_allowed_weights = subnet['max_allowed_weights']
    
        if len(uids) == 0:
            c.print(f'No uids to vote on.')
            return False
        if len(uids) > max_allowed_weights:
            c.print(f'Only {max_allowed_weights} uids are allowed to be voted on.')
            uids = uids[:max_allowed_weights]

        
        if len(uids) < min_allowed_weights:
            while len(uids) < min_allowed_weights:
                uid = c.choice(list(range(subnet['n'])))
                if uid not in uids:
                    uids.append(uid)
                    weights.append(0)
            
        if weights is None:
            weights = [1 for _ in uids]
        if isinstance(weights, list):
            weights = torch.tensor(weights)

        weights = weights / weights.sum()
        weights = weights * U16_MAX
        weights = weights.tolist()

        # uids = [int(uid) for uid in uids]
        uid2weight = {uid: int(weight) for uid, weight in zip(uids, weights) if int(weight) > 0}
        uids = list(uid2weight.keys())
        weights = list(uid2weight.values())
        
        c.print(f'Weights: {weights} from {key}')
        
        c.print(f'Setting weights for {len(uids)} uids..., {len(weights)}')
        # First convert types.

        with self.substrate as substrate:
            call = substrate.compose_call(
                call_module='SubspaceModule',
                call_function='set_weights',
                call_params = {
                    'uids': uids,
                    'weights': weights,
                    'netuid': netuid,
                }
            )
        # Period dictates how long the extrinsic will stay as part of waiting pool
        c.print(key)
        extrinsic = substrate.create_signed_extrinsic( call = call, keypair = key, era={'period':100})

        c.print(f'Submitting extrinsic: {extrinsic}')
        response = substrate.submit_extrinsic( extrinsic, wait_for_inclusion = wait_for_inclusion,
                                              wait_for_finalization = wait_for_finalization )
        # We only wait here if we expect finalization.
        if not wait_for_finalization and not wait_for_inclusion:
            c.print(":white_heavy_check_mark: [green]Sent[/green]")
            return True
        response.process_events()
        if response.is_success:
            c.print(":white_heavy_check_mark: [green]Finalized[/green]")            
            c.print(f"Set weights:\n[bold white]  weights: {weights}\n  uids: {uids}[/bold white ]")
            return True
        else:
            c.print(":cross_mark: [red]Failed[/red]: error:{}".format(response.error_message))
            c.print(  'Set weights <red>Failed: </red>' + str(response.error_message) )
            return False

    set_weights = vote

    def get_netuid_for_subnet(self, network: str = None) -> int:
        netuid = self.subnet_namespace.get(network, None)
        return netuid

    def update(self):
        self.sync()


    @classmethod
    def up(cls):
        c.cmd('docker-compose up -d', cwd=cls.chain_path)

    @classmethod
    def enter(cls):
        c.cmd('make enter', cwd=cls.chain_path)

    def register_servers(self, **kwargs):
        for m in c.servers(network='local'):
            self.register(name=m, **kwargs)
    reg_servers = register_servers
    def reged_servers(self, **kwargs):
        servers =  c.servers(network='local')
        c.print(servers)
    def register_ghosts(self, n=10, **kwargs):
        ip = c.ip()
        for i in range(n):
            self.register(name=f'ghost{i}',
                         address= ip + ':' + str(8000 + i), 
                          **kwargs)


    def register(
        self,
        name: str , # defaults to module.tage
        stake : float = 0,
        subnet: str = None,
        key : str  = None,
        address : str = None,
        wait_for_inclusion: bool = False,
        wait_for_finalization: bool = True,
        network: str = network,
        existential_balance: float = 0.1,
        sync: bool = False,

    ) -> bool:
        
        assert name != None, f"Module name must be provided"

        if subnet == None:
            subnet = self.config.subnet


        network =self.resolve_network(network)
        address = c.namespace(network='local').get(name, address)
        address = address.replace('0.0.0.0',c.ip())
        key = self.resolve_key(name)

        if self.subnet_exists(subnet, network=network):
            netuid = self.get_netuid_for_subnet(subnet)
            if self.is_registered(key.ss58_address, netuid=netuid):
                return self.update_module(module=name, name=name, address=address , netuid=netuid, network=network)

        call_params = { 
                    'network': subnet.encode('utf-8'),
                    'address': address.encode('utf-8'),
                    'name': name.encode('utf-8'),
                    'stake': stake,
                } 
        # key symbol
        c.print(f":satellite: Registering (name = {name} key (ss58) = {key.ss58_address[:4]}.. address {address} ")

        with self.substrate as substrate:
            
            # create extrinsic call
            call = substrate.compose_call( 
                call_module='SubspaceModule',  
                call_function='register', 
                call_params=call_params
            )
            extrinsic = substrate.create_signed_extrinsic( call = call, keypair = key  )
            response = substrate.submit_extrinsic( extrinsic, wait_for_inclusion=wait_for_inclusion, wait_for_finalization=wait_for_finalization )
            
            # process if registration successful, try again if pow is still valid
            response.process_events()
            
        if response.is_success:
            msg = f'Registered {name} with address {address}'
            c.print(f":white_heavy_check_mark: [green]{msg}[/green]")
            return {'success': True, 'message': msg}
            # if sync:
            #     self.sync()
        else:
            msg = response.error_message
            c.print(f":cross_mark: [red]Failed[/red]: error:{response.error_message}")
            return {'success': False, 'message': response.error_message}    
        

    reg = register

    ##################
    #### Transfer ####
    ##################
    def transfer(
        self,
        key: str,
        amount: float , 
        dest: str, 
        wait_for_inclusion: bool = True,
        wait_for_finalization: bool = False,
        network : str = None,
        netuid : int = None,
    ) -> bool:
        key = c.get_key(key)
        network = self.resolve_network(network)
        dest = self.resolve_module_key(dest, netuid=netuid)
        # Validate destination address.
        if not is_valid_address_or_public_key( dest ):
            msg = ":cross_mark: [red]Invalid destination address[/red]:[bold white]\n  {}[/bold white]".format(dest)
            return {'success': False, 'message': msg}
        if isinstance( dest, bytes):
            # Convert bytes to hex string.
            dest = "0x" + dest.hex()


        # Check balance.
        account_balance = self.get_balance( key.ss58_address , fmt='nano' )
        transfer_balance = self.to_nanos(amount)

        if transfer_balance > account_balance:
            c.print(":cross_mark: [red]Insufficient balance[/red]:[bold white]\n  {}[/bold white]".format(account_balance))
            return
        c.print(f"Transferring {amount} to {dest}")

        with c.status(":satellite: Transferring to {}"):
            with self.substrate as substrate:
                call = substrate.compose_call(
                    call_module='Balances',
                    call_function='transfer',
                    call_params={
                        'dest': dest, 
                        'value': transfer_balance
                    }
                )

                extrinsic = substrate.create_signed_extrinsic( call = call, keypair = key )
                response = substrate.submit_extrinsic( extrinsic, wait_for_inclusion = wait_for_inclusion, wait_for_finalization = wait_for_finalization )
                # We only wait here if we expect finalization.
                if not wait_for_finalization and not wait_for_inclusion:
                    c.print(":white_heavy_check_mark: [green]Sent[/green]")
                    return True

                # Otherwise continue with finalization.
                response.process_events()
                if response.is_success:
                    c.print(":white_heavy_check_mark: [green]Finalized[/green]")
                    block_hash = response.block_hash
                    c.print("[green]Block Hash: {}[/green]".format( block_hash ))
                    new_balance = self.get_balance( key.ss58_address , fmt='j')
                    account_balance = self.format_amount(account_balance, fmt='j')
                    c.print("Balance:\n  [blue]{}[/blue] :arrow_right: [green]{}[/green]".format(account_balance, new_balance))
                    return {'success': True, 'message': 'Successfully transferred {} to {}'.format(amount, dest)}
                else:
                    c.print(":cross_mark: [red]Failed[/red]: error:{}".format(response.error_message))
                    return {'success': False, 'message': response.error_message}


        
        return False
    
    def get_existential_deposit(
        self,
        block: Optional[int] = None,
        fmt = 'nano'
    ) -> Optional[Balance]:
        """ Returns the existential deposit for the chain. """
        result = self.query_constant(
            module_name='Balances',
            constant_name='ExistentialDeposit',
            block = block,
        )
        
        if result is None:
            return None
        
        return self.format_amount( result.value, fmt = fmt )
        
    #################
    #### Serving ####
    #################
    def update_module(
        self,
        module: str,
        # params from here
        name: str = None,
        address: str = None,
        netuid: int = None,
        wait_for_inclusion: bool = False,
        wait_for_finalization = True,
        network : str = network,

    ) -> bool:
        self.resolve_network(network)
        key = self.resolve_key(module)
        netuid = self.resolve_netuid(netuid)  
        module_info = self.get_module(module)

        if name == None:
            name = module
    
        if address == None:
            namespace_local = c.namespace(network='local')
            address = namespace_local.get(name,  f'{c.ip()}:{c.free_port()}'  )

        if name == module_info['name'] and address == module_info['address']:
            c.print(f"{c.emoji('check_mark')} [green] [white]{module}[/white] Module already registered and is up to date[/green]:[bold white][/bold white]")
            return {'success': False, 'message': f'{module} already registered and is up to date with your changes'}
        call_params = {
            'name': name,
            'address': address,
            'netuid': netuid,
        }

        for k in ['name', 'address']:
            if call_params[k] == module_info[k]:
                call_params[k] = ''


        with self.substrate as substrate:
            c.print(f':satellite: Updating Module: [bold white]{name}[/bold white] \n\n {call_params}')
            
            call = substrate.compose_call(
                call_module='SubspaceModule',
                call_function='update_module',
                call_params =call_params
            )
            extrinsic = substrate.create_signed_extrinsic( call = call, keypair = key)
            response = substrate.submit_extrinsic( extrinsic, wait_for_inclusion = wait_for_inclusion, wait_for_finalization = wait_for_finalization )
            if wait_for_inclusion or wait_for_finalization:
                response.process_events()
                if response.is_success:
                    msg = 'Updated Module'
                    c.print(f':white_heavy_check_mark: [green]{msg}[/green]\n  [bold white]{call_params}[/bold white]')
                    # if we rename the module, we need to move the key from the module (old name) to the new name
                    old_name = module
                    if old_name != name:
                        c.switch_key(old_name,name)
                    return {'success': True, 'msg': msg}
                else:
                    msg = response.error_message
                    c.print( f':cross_mark: error: {msg}')
                    return {'success': False, 'msg': msg}



    #################
    #### Serving ####
    #################
    def update_network (
        self,
        netuid: int = None,
        immunity_period: int = None,
        min_allowed_weights: int = None,
        max_allowed_weights: int = None,
        max_allowed_uids: int = None,
        tempo: int = None,
        name:str = None,
        founder: str = None,
        wait_for_inclusion: bool = False,
        wait_for_finalization = True,
        key: str = None,
        network = network,
        prompt: bool = False,
    ) -> bool:
            
        self.resolve_network(network)
        netuid = self.resolve_netuid(netuid)
        subnet_state = self.subnet_state( netuid=netuid )
        # infer the key if you have it
        if key == None:
            key2address = self.address2key()
            if subnet_state['founder'] not in key2address:
                return {'success': False, 'message': f"Subnet {netuid} not found in local namespace, please deploy it "}
            key = c.get_key(key2address.get(subnet_state['founder']))
            c.print(f'Using key: {key}')

        
        params = {
            'immunity_period': immunity_period,
            'min_allowed_weights': min_allowed_weights,
            'max_allowed_uids': max_allowed_uids,
            'max_allowed_weights': max_allowed_weights,
            'tempo': tempo,
            'founder': founder,
            'name': name,
        }
        old_params = {}
        for k, v in params.items():
            old_params[k] = subnet_state[k]
            if v == None:
                params[k] = old_params[k]
        name = subnet_state['name']
        call_params = {'netuid': netuid, **params}

        with self.substrate as substrate:
            c.print(f':satellite: Updating Subnet:({name}, id: {netuid})')
            c.print(f'  [bold yellow]Old Params:[/bold yellow] \n', old_params)
            c.print(f'  [bold green]New Params:[/bold green] \n',params)
            call = substrate.compose_call(
                call_module='SubspaceModule',
                call_function='update_network',
                call_params =call_params
            )
            extrinsic = substrate.create_signed_extrinsic( call = call, keypair = key)
            response = substrate.submit_extrinsic( extrinsic, wait_for_inclusion = wait_for_inclusion, wait_for_finalization = wait_for_finalization )
            if wait_for_inclusion or wait_for_finalization:
                response.process_events()
                if response.is_success:
                    c.print(f':white_heavy_check_mark: [green]Updated SubNetwork ({name}, id: {netuid}) [/green]')
                    return True
                else:
                    c.print(f':cross_mark: [red]Failed to Change Subnetwork[/red] ({name}, id: {netuid}) error: {response.error_message}')
                    return False
            else:
                return True

    def get_unique_tag(self, module:str, tag:str=None, netuid:int=None, **kwargs):
        if tag == None:
            tag = ''
        name = f'{module}{tag}'
        return self.resolve_unique_server_name(name=name, netuid=netuid, **kwargs).split('::')[-1]

    def resolve_unique_server_names(self, name:str,  n:int=10,   **kwargs) -> List[str]:
        server_names = []
        for i in range(n):
            server_name = self.resolve_unique_server_name(name=name, n=n, avoid_servers=server_names, **kwargs)

            server_names += [server_name]

        return server_names

            



    def resolve_unique_server_name(self, name:str, tag:str = None, netuid:Union[str, int]=None , avoid_servers:List[str]=None , tag_seperator = '::',  **kwargs): 

        cnt = 0
        if tag == None:
            tag = ''
        name = name + tag_seperator + tag
        servers = self.servers(netuid=netuid,**kwargs)
        if avoid_servers == None:
            avoid_servers = []
        servers += avoid_servers
        new_name = name
        while new_name in servers:
            new_name = name + str(cnt)
            cnt += 1

        c.print(new_name)

        return new_name

    def resolve_module_key(self, module_key: str =None, key: str =None, netuid: int = None):
        if module_key == None:
            assert key != None, "Please provide a key"
            module_key = key.ss58_address
        elif isinstance(module_key, str):
            if c.key_exists(module_key):
                module_key = c.get_key(module_key).ss58_address
            else:
                module2key =self.module2key(netuid=netuid)
                if module_key in module2key:
                    module_key = module2key[module_key]

        assert module_key != None, "Please provide a module_key"
        return module_key




    def transfer_stake(
            self,
            key: str ,
            new_module_key: str = None,
            module_key: str = None,
            amount: Union[Balance, float] = None, 
            netuid:int = None,
            wait_for_inclusion: bool = False,
            wait_for_finalization: bool = True,
            network:str = None,
            existential_deposit: float = 0.1,
            sync: bool = False
        ) -> bool:
        raise NotImplementedError
        # STILL UNDER DEVELOPMENT, DO NOT USE
        network = self.resolve_network(network)
        netuid = self.resolve_netuid(netuid)
        key = c.get_key(key)

        c.print(f':satellite: Staking to: [bold white]SubNetwork {netuid}[/bold white] {amount} ...')
        # Flag to indicate if we are using the wallet's own hotkey.
        old_balance = self.get_balance( key.ss58_address , fmt='j')
        module_key = self.resolve_module_key(module_key=module_key, key=key, netuid=netuid)
        new_module_key = self.resolve_module_key(module_key=new_module_key, key=key, netuid=netuid)

        if not self.is_registered( module_key, netuid=netuid):
            return {'success': False, 'message': f"Module {module_key} not registered in SubNetwork {netuid}"}
        
        old_stake = self.get_stake_from( module_key, from_key=key.ss58_address , fmt='j', netuid=netuid)
        if amount is None:
            amount = old_balance
        amount = self.to_nanos(amount - existential_deposit)
        
        # Get current stake
        call_params={
                    'netuid': netuid,
                    'amount': int(amount),
                    'module_key': module_key
                    }
    
        c.print(call_params)

        with c.status(":satellite: Staking to: [bold white]{}[/bold white] ...".format(self.network)):

            with self.substrate as substrate:
                call = substrate.compose_call(
                call_module='SubspaceModule', 
                call_function='add_stake',
                call_params=call_params
                )
                extrinsic = substrate.create_signed_extrinsic( call = call, keypair = key )
                response = substrate.submit_extrinsic( extrinsic, 
                                                        wait_for_inclusion = wait_for_inclusion,
                                                        wait_for_finalization = wait_for_finalization )

        if response.is_success:
            c.print(":white_heavy_check_mark: [green]Sent[/green]")
            new_balance = self.get_balance(  key.ss58_address , fmt='j')
            c.print(f"Balance ({key.ss58_address}):\n  [blue]{old_balance}[/blue] :arrow_right: [green]{new_balance}[/green]")
            new_stake = self.get_stake_from( module_key, from_key=key.ss58_address , fmt='j', netuid=netuid)
            c.print(f"Stake ({module_key}):\n  [blue]{old_stake}[/blue] :arrow_right: [green]{new_stake}[/green]")
                
        else:
            c.print(":cross_mark: [red]Stake Error: {}[/red]".format(response.error_message))


        if sync:
            self.sync()



    def stake(
            self,
            key: str ,
            amount: Union[Balance, float] = None, 
            module_key: Optional[str] = None, # defaults to key if not provided
            netuid:int = None,
            wait_for_inclusion: bool = False,
            wait_for_finalization: bool = True,
            network:str = None,
            existential_deposit: float = 0.0,
            sync: bool = False
        ) -> bool:
        network = self.resolve_network(network)
        netuid = self.resolve_netuid(netuid)
        key = c.get_key(key)

        c.print(f':satellite: Staking to: [bold white]SubNetwork {netuid}[/bold white] {amount} ...')
        # Flag to indicate if we are using the wallet's own hotkey.
        old_balance = self.get_balance( key.ss58_address , fmt='j')
        module_key = self.resolve_module_key(module_key=module_key, key=key, netuid=netuid)
        old_stake = self.get_stake_from( module_key, from_key=key.ss58_address , fmt='j', netuid=netuid)
        if amount is None:
            amount = old_balance
        amount = self.to_nanos(amount - existential_deposit)
        
        # Get current stake
        call_params={
                    'netuid': netuid,
                    'amount': int(amount),
                    'module_key': module_key
                    }

        with c.status(":satellite: Staking to: [bold white]{}[/bold white] ...".format(self.network)):

            with self.substrate as substrate:

                call = substrate.compose_call( call_module='SubspaceModule', 
                                                call_function='add_stake',
                                                call_params=call_params
                                                )

                extrinsic = substrate.create_signed_extrinsic( call = call, keypair = key )
                response = substrate.submit_extrinsic( extrinsic, 
                                                        wait_for_inclusion = wait_for_inclusion,
                                                        wait_for_finalization = wait_for_finalization )

        if response.is_success:
            c.print(":white_heavy_check_mark: [green]Sent[/green]")
            new_stake = self.get_stake_from( module_key, from_key=key.ss58_address , fmt='j', netuid=netuid)
            c.print(f"Stake ({module_key[:4]}..):\n  [blue]{old_stake}[/blue] :arrow_right: [green]{new_stake}[/green]")

            new_balance = self.get_balance(  key.ss58_address , fmt='j')
            c.print(f"Balance ({key.ss58_address}...):\n  [blue]{old_balance}[/blue] :arrow_right: [green]{new_balance}[/green]")
                
        else:
            c.print(":cross_mark: [red]Stake Error: {}[/red]".format(response.error_message))


        if sync:
            self.sync()



    def unstake(
            self,
            key : 'c.Key', 
            amount: float = None, 
            module_key : str = None,
            netuid : Union[str, int] = None,
            wait_for_inclusion:bool = True, 
            wait_for_finalization:bool = False,
            prompt: bool = False,
            network: str= None,
            sync: bool = True
        ) -> bool:
        network = self.resolve_network(network)
        key = c.get_key(key)
        netuid = self.resolve_netuid(netuid)
        
        module_key = self.resolve_module_key(module_key=module_key, key=key, netuid=netuid)
        old_balance = self.get_balance( key , fmt='j')

        old_stake = self.get_stake_to( key.ss58_address, to_key=module_key,  netuid=netuid, fmt='j',)

        if amount == None:
            amount = old_stake

        amount = self.to_nanos(amount)
        call_params={
            'amount': amount,
            'netuid': netuid,
            'module_key': module_key
            }
        c.print(call_params)
        with c.status(":satellite: Unstaking from chain: [white]{}[/white] ...".format(self.network)):

            with self.substrate as substrate:
                call = substrate.compose_call(
                call_module='SubspaceModule', 
                call_function='remove_stake',
                call_params=call_params
                )
                extrinsic = substrate.create_signed_extrinsic( call = call, keypair = key )
                response = substrate.submit_extrinsic( extrinsic, wait_for_inclusion = wait_for_inclusion, wait_for_finalization = wait_for_finalization )
                # We only wait here if we expect finalization.
                if not wait_for_finalization and not wait_for_inclusion:
                    return True

                response.process_events()


        if response.is_success: # If we successfully unstaked.
            c.print(":white_heavy_check_mark: [green]Finalized[/green]")
            with c.status(":satellite: Checking Balance on: [white]{}[/white] ...".format(self.network)):

                new_balance = self.get_balance( key.ss58_address , fmt='j')
                c.print(f"Balance ({key.ss58_address}):\n  [blue]{old_balance}[/blue] :arrow_right: [green]{new_balance}[/green]")

                new_stake = self.get_stake_from(module_key, from_key=key.ss58_address , fmt='j') # Get stake on hotkey.
                c.print(f"Stake ({module_key}) :\n  [blue]{old_stake}[/blue] :arrow_right: [green]{new_stake}[/green]")


        else:
            c.print(":cross_mark: [red]Failed[/red]: Error unknown.")

        if sync:
            self.sync()

        return {'success': True, 'message': 'Successfully unstaked {} from {}'.format(amount, module_key)}
            
    ########################
    #### Standard Calls ####
    ########################

    """ Queries subspace named storage with params and block. """
    @retry(delay=2, tries=3, backoff=2, max_delay=4)
    def query_subspace( self, name: str,
                       params: Optional[List[object]] = [], 
                        block: Optional[int] = None, 

                       network=None ) -> Optional[object]:
        network = self.resolve_network(network)
        
        with self.substrate as substrate:
            return substrate.query(
                module='SubspaceModule',
                storage_function = name,
                params = params,
                block_hash = None if block == None else substrate.get_block_hash(block)
                )

    def stake_from(self, netuid = None, block=None):
        netuid  = self.resolve_netuid(netuid)
        return {k.value: list(map(list,v.value)) for k,v in self.query_map('StakeFrom', netuid, block=block)}
    
    def stake_to(self, netuid = None, network=None, block=None):
        network = self.resolve_network(network)
        netuid  = self.resolve_netuid(netuid)
        return {k.value: list(map(list,v.value)) for k,v in self.query_map('StakeTo', netuid, block=block)}

    """ Queries subspace map storage with params and block. """
    def query_map( self, 
                 name: str, 
                  params: list = None,
                  block: Optional[int] = None, 
                  network:str = None,
                  max_age = 60,
                  page_size=1000,
                  max_results=100000,
                  records = True
                  
                  ) -> Optional[object]:
        network = self.resolve_network(network)

        if params == None:
            params = []

        if params != None and not isinstance(params, list):
            params = [params]
        
        with self.substrate as substrate:
            block_hash = None if block == None else substrate.get_block_hash(block)
            qmap =  substrate.query_map(
                module='SubspaceModule',
                storage_function = name,
                params = params,
                page_size = page_size,
                max_results = max_results,
                block_hash =block_hash
            )

            qmap = [(k,v) for k,v  in qmap]
                
        return qmap
        
    """ Gets a constant from subspace with module_name, constant_name, and block. """
    def query_constant( self, 
                        constant_name: str, 
                       module_name: str = 'SubspaceModule', 
                       block: Optional[int] = None ,
                       network: str = None) -> Optional[object]:
        
        network = self.resolve_network(network)

        with self.substrate as substrate:
            value =  substrate.query(
                module=module_name,
                storage_function=constant_name,
                block_hash = None if block == None else substrate.get_block_hash(block)
            )
            
        c.print("Constant: [bold white]{}[/bold white] = [bold green]{}[/bold green]".format(constant_name, value))
        return value
            
    def stale_modules(self, *args, **kwargs):
        modules = self.my_modules(*args, **kwargs)
        servers = c.servers(network='local')
        servers = c.shuffle(servers)
        return [m['name'] for m in modules if m['name'] not in servers]

    #####################################
    #### Hyper parameter calls. ####
    #####################################

    """ Returns network ImmunityPeriod hyper parameter """
    def immunity_period (self, netuid: int = None, block: Optional[int] = None, network :str = None ) -> Optional[int]:
        netuid = self.resolve_netuid( netuid )
        return self.query("ImmunityPeriod",params=netuid, block=block ).value


    """ Returns network MinAllowedWeights hyper parameter """
    def min_allowed_weights (self, netuid: int = None, block: Optional[int] = None ) -> Optional[int]:
        netuid = self.resolve_netuid( netuid )
        return self.query("MinAllowedWeights", params=[netuid], block=block).value
    """ Returns network MinAllowedWeights hyper parameter """
    def max_allowed_weights (self, netuid: int = None, block: Optional[int] = None ) -> Optional[int]:
        netuid = self.resolve_netuid( netuid )
        return self.query("MaxAllowedWeights", params=[netuid], block=block).value

    """ Returns network SubnetN hyper parameter """
    def n(self, network = network , netuid: int = None, block: Optional[int] = None ) -> int:
        self.resolve_network(network)
        netuid = self.resolve_netuid( netuid )
        return self.query('N', netuid, block=block ).value

    """ Returns network MaxAllowedUids hyper parameter """
    def max_allowed_uids (self, netuid: int = None, block: Optional[int] = None ) -> Optional[int]:
        netuid = self.resolve_netuid( netuid )
        return self.query('MaxAllowedUids', netuid, block=block ).value

    """ Returns network Tempo hyper parameter """
    def tempo (self, netuid: int = None, block: Optional[int] = None) -> int:
        netuid = self.resolve_netuid( netuid )
        return self.query('Tempo', params=[netuid], block=block).value

    ##########################
    #### Account functions ###
    ##########################
    
    """ Returns network Tempo hyper parameter """
    def stakes(self, netuid: int = None, block: Optional[int] = None, fmt:str='nano') -> int:
        netuid = self.resolve_netuid( netuid )
        return {k.value: self.format_amount(v.value, fmt=fmt) for k,v in self.query_map('Stake', netuid )}

    """ Returns the stake under a coldkey - hotkey pairing """
    
    
    
    @classmethod
    def resolve_key_ss58(cls, key_ss58):
        
        if isinstance(key_ss58, str):
            if key_ss58 in c.keys():
                key_ss58 = c.get_key( key_ss58 )
            
        if hasattr(key_ss58, 'ss58_address'):
            key_ss58 = key_ss58.ss58_address
        return key_ss58


    @classmethod
    def resolve_key(cls, key, create:bool = True):
        if isinstance(key, str):
            if not c.key_exists( key ) and create:
                c.add_key( key)
            key = c.get_key( key )
        assert hasattr(key, 'ss58_address'), f"Invalid Key {key} as it should have ss58_address attribute."
        return key
        
    @classmethod
    def from_nano(cls,x):
        return x / (10**cls.token_decimals)
    to_token = from_nano
    @classmethod
    def to_nanos(cls,x):
        return x * (10**cls.token_decimals)
    from_token = to_nanos
    @classmethod
    def format_amount(cls, x, fmt='nano'):
        if fmt in ['nano', 'n']:
            return x
        elif fmt in ['token', 'unit', 'j', 'J']:
            return cls.to_token(x)
        else:
            raise ValueError(f"Invalid format {fmt}.")
    
    def get_stake( self, key_ss58: str, block: Optional[int] = None, netuid:int = None , fmt='j' ) -> Optional['Balance']:
        
        key_ss58 = self.resolve_key_ss58( key_ss58 )
        netuid = self.resolve_netuid( netuid )
        stake = self.query( 'Stake',params=[netuid, key_ss58], block=block ).value
        return self.format_amount(stake, fmt=fmt)


    def get_staked_modules(self, key : str , netuid=None, **kwargs) -> Optional['Balance']:
        modules = self.modules(netuid=netuid, **kwargs)
        key_address = self.resolve_key_ss58( key )
        staked_modules = {}
        for module in modules:
            for k,v in module['stake_from']:
                if k == key_address:
                    staked_modules[module['name']] = v

        return staked_modules
        

    def get_stake_to( self, key: str, to_key=None, block: Optional[int] = None, netuid:int = None , fmt='j' , return_names = False) -> Optional['Balance']:
        
        key_address = self.resolve_key_ss58( key )
        netuid = self.resolve_netuid( netuid )
        stake_to =  [(k.value, self.format_amount(v.value, fmt=fmt)) for k, v in self.query( 'StakeTo', params=[netuid, key_address], block=block )]

        if to_key is not None:
            to_key_address = self.resolve_key_ss58( to_key )
            stake_to ={ k:v for k, v in stake_to}.get(to_key_address, 0)
        return stake_to
    

    def get_stakers( self, key: str, block: Optional[int] = None, netuid:int = None , fmt='j' ) -> Optional['Balance']:
        stake_from = self.get_stake_from(key=key, block=block, netuid=netuid, fmt=fmt)
        key2module = self.key2module(netuid=netuid)
        return {key2module[k]['name'] : v for k,v in stake_from}
        
    def get_stake_from( self, key: str, from_key=None, block: Optional[int] = None, netuid:int = None, fmt='j'  ) -> Optional['Balance']:
        key2module = self.key2module(netuid=netuid)
        key = self.resolve_key_ss58( key )
        netuid = self.resolve_netuid( netuid )
        state_from =  [(k.value, self.format_amount(v.value, fmt=fmt)) for k, v in self.query( 'StakeFrom', block=block, params=[netuid, key] )]
 
        if from_key is not None:
            from_key = self.resolve_key_ss58( from_key )
            state_from ={ k:v for k, v in state_from}.get(from_key, 0)

        return state_from

    def unstake_all( self, key: str, netuid:int = None  ) -> Optional['Balance']:
        
        key = self.resolve_key( key )
        netuid = self.resolve_netuid( netuid )
        stake_to =  self.get_stake_to( key, netuid=netuid )
        c.print(f"Unstaking all for [bold white]{key}[/bold white] on network [bold white]{netuid}[/bold white]. -> {stake_to}")
        for (module_key, stake_amount) in stake_to:
            self.unstake( key=key, module_key=module_key, netuid=netuid, amount=stake_amount)
       

    def stake_multiple( self, 
                        key: str, 
                        modules:list = None,
                        amounts:Union[list, float, int] = None,
                        netuid:int = None,
                        network: str = None) -> Optional['Balance']:
        self.resolve_network( network )
        key = self.resolve_key( key )
        balance = self.get_balance(key=key, fmt='j')
        if modules is None:
            modules = [m['name'] for m in self.my_modules(netuid=netuid)]  
        if amounts is None:
            amounts = [balance/len(modules)] * len(modules)
        if isinstance(amounts, (float, int)): 
            amounts = [amounts] * len(modules)
        assert len(modules) == len(amounts), f"Length of modules and amounts must be the same. Got {len(modules)} and {len(amounts)}."
        
        module2key = self.module2key(netuid=netuid)
        
        if balance < sum(amounts):
            return {'error': f"Insufficient balance. {balance} < {sum(amounts)}"}
        module2amount = {module:amount for module, amount in zip(modules, amounts)}
        c.print(f"Staking {module2amount} for [bold white]{key.ss58_address}[/bold white] on network [bold white]{netuid}[/bold white].")

        for module, amount in module2amount.items():
            module_key = module2key[module]
            self.stake( key=key, module_key=module_key, netuid=netuid, amount=amount)
       
    ###########################
    #### Global Parameters ####
    ###########################

    @property
    def block(self, network:str=None) -> int:
        return self.get_current_block(network=network)

    def total_stake (self,block: Optional[int] = None ) -> 'Balance':
        return Balance.from_nano( self.query( "TotalStake", block=block ).value )



    @classmethod
    def archived_blocks(cls, network:str=network, reverse:bool = True) -> List[int]:
        # returns a list of archived blocks 
        
        blocks =  [f.split('.B')[-1].split('.json')[0] for f in cls.glob(f'archive/{network}/state.B*')]
        blocks = [int(b) for b in blocks]
        sorted_blocks = sorted(blocks, reverse=reverse)
        return sorted_blocks

    @classmethod
    def oldest_archive_path(cls, network:str=network) -> str:
        oldest_archive_block = cls.oldest_archive_block(network=network)
        assert oldest_archive_block != None, f"No archives found for network {network}"
        return cls.resolve_path(f'state_dict/{network}/state.B{oldest_archive_block}.json')
    @classmethod
    def newest_archive_block(cls, network:str=network) -> str:
        blocks = cls.archived_blocks(network=network, reverse=True)
        return blocks[0]
    @classmethod
    def newest_archive_path(cls, network:str=network) -> str:
        oldest_archive_block = cls.newest_archive_block(network=network)
        return cls.resolve_path(f'archive/{network}/state.B{oldest_archive_block}.json')
    @classmethod
    def oldest_archive_block(cls, network:str=network) -> str:
        blocks = cls.archived_blocks(network=network, reverse=True)
        if len(blocks) == 0:
            return None
        return blocks[-1]

        
    @classmethod
    def loop(cls, 
                network = network,
                netuid:int = None,
                 interval:dict= 100,
                 sleep:float=1,
                 remote:bool=True):
        if remote:
            kwargs = c.locals2kwargs(locals())
            kwargs['remote'] = False
            return cls.remote_fn('loop', kwargs=kwargs)
            
        
        time_start = c.time()
        while True:
            c.sleep(sleep)
            current_time = c.time()
            time_since_last = int(current_time - time_start)

            if time_since_last > interval:
                self = cls(network=network, netuid=netuid)
                c.print(self.sync(), color='green')
                self.register_servers()
                 
                time_start = current_time

            c.print(f"Looping {time_since_last} / {interval}", color='yellow')
            
            
    
    
    state_dict_cache = {}
    def state_dict(self,
                    network=network, 
                    key: Union[str, list]=None, 
                    inlcude_weights:bool=False, 
                    update:bool=False, 
                    verbose:bool=False, 
                    **kwargs):
        # cache and update are mutually exclusive 
        if  update == False:
            c.print('Loading state_dict from cache', verbose=verbose)
            state_dict = self.latest_archive(network=network)
            if len(state_dict) > 0:
                self.state_dict_cache = state_dict


        if len(self.state_dict_cache) == 0 :
            block = self.block
            netuids = self.netuids()
            state_dict = {'subnets': [self.subnet_state(netuid=netuid, network=network, block=block, cache=False) for netuid in netuids], 
                        'modules': [self.modules(netuid=netuid, network=network, include_weights=inlcude_weights, block=block, cache=False) for netuid in netuids],
                        'stake_to': [self.stake_to(network=network, block=block) for netuid in netuids],
                        'balances': self.balances(network=network, block=block),
                        'block': block,
                        'network': network,
                        }

            path = f'state_dict/{network}.block-{block}-time-{int(c.time())}'
            c.print(f'Saving state_dict to {path}', verbose=verbose)

            
            self.put(path, state_dict) # put it in storage
            self.state_dict_cache = state_dict # update it in memory

        state_dict = c.copy(self.state_dict_cache)
        if key in state_dict:
            return state_dict[key]
        if isinstance(key,list):
            return {k:state_dict[k] for k in key}
        
        return state_dict
    @classmethod
    def ls_archives(cls, network=network):
        if network == None:
            network = cls.network 
        return [f for f in cls.ls(f'state_dict') if os.path.basename(f).startswith(network)]

    
    @classmethod
    def block2archive(cls, network=network):
        paths = cls.ls_archives(network=network)

        block2archive = {int(p.split('-')[-1].split('-time')[0]):p for p in paths if p.endswith('.json') and f'{network}.block-' in p}
        return block2archive
    @classmethod
    def time2archive(cls, network=network):
        paths = cls.ls_archives(network=network)

        block2archive = {int(p.split('time-')[-1].split('.json')[0]):p for p in paths if p.endswith('.json') and f'time-' in p}
        return block2archive

    @classmethod
    def datetime2archive(cls, network=network):
        time2archive = cls.time2archive(network=network)
        datetime2archive = {c.time2datetime(time):archive for time,archive in time2archive.items()}
        # sort by datetime
        # 
        datetime2archive = {k:v for k,v in sorted(datetime2archive.items(), key=lambda x: x[0])}
        return datetime2archive



    @classmethod
    def latest_archive_path(cls, network=network):
        latest_archive_time = cls.latest_archive_time(network=network)
    
        if latest_archive_time == None:
            return None
        time2archive = cls.time2archive(network=network)
        return time2archive[latest_archive_time]

    @classmethod
    def latest_archive_time(cls, network=network):
        time2archive = cls.time2archive(network=network)
        if len(time2archive) == 0:
            return None
        latest_time = max(time2archive.keys())
        return latest_time

    @classmethod
    def latest_archive_datetime(cls, network=network):
        latest_archive_time = cls.latest_archive_time(network=network)
        assert latest_archive_time != None, f"No archives found for network {network}"
        return c.time2datetime(latest_archive_time)

    @classmethod
    def archive_staleness(self, network=network):
        return c.time() - self.latest_archive_time(network=network)

    @classmethod
    def latest_archive(cls, network=network):
        path = cls.latest_archive_path(network=network)
        if path == None:
            return {}
        return cls.get(path, {})
            
        


    
    def sync(self, network=None, remote:bool=True, local:bool=True, save:bool=True):
        network = self.resolve_network(network)
        self.state_dict(update=True, network=network)
        return {'success': True, 'message': f'Successfully saved {network} locally at block {self.block}'}

    def sync_loop(self, interval=60, network=None, remote:bool=True, local:bool=True, save:bool=True):
        while True:
            self.sync(network=network, remote=remote, local=local, save=save)
            c.sleep(interval)

    def subnet_exists(self, subnet:str, network=None) -> bool:
        subnets = self.subnets(network=network)
        return bool(subnet in subnets)

    def subnet_states(self, *args, **kwargs):

        subnet_states = []
        for netuid in self.netuids():
            subnet_state = self.subnet_state(*args,  netuid=netuid, **kwargs)
            subnet_states.append(subnet_state)
        return subnet_states


    def total_stake(self, network=network, block: Optional[int] = None, fmt='j') -> 'Balance':
        self.resolve_network(network)
        return self.format_amount(self.query_constant( "TotalStake", block=block, network=network ).value, fmt=fmt)

    def total_balance(self, network=network, block: Optional[int] = None, fmt='j') -> 'Balance':
        return sum(list(self.balances(network=network, block=block, fmt=fmt).values()))

    def total_supply(self, network=network, block: Optional[int] = None, fmt='j') -> 'Balance':
        return self.total_stake(network=network, block=block) + self.total_balance(network=network, block=block, fmt=fmt)
            
    
    def subnet_state(self, 
                    netuid=netuid,
                    network = network,
                    update: bool = False,
                    block : Optional[int] = None,
                    cache:bool = True) -> list:
        
        
        if cache and not update:
            subnet_states =  self.state_dict(network=network, key='subnets', update=update )
            if len(subnet_states) > netuid:
                return subnet_states[netuid]
        subnet_stake = self.query( 'SubnetTotalStake', params=netuid , block=block).value
        subnet_emission = self.query( 'SubnetEmission', params=netuid, block=block ).value
        subnet_founder = self.query( 'Founder', params=netuid, block=block ).value
        n = self.query( 'N', params=netuid, block=block ).value
        total_stake = self.total_stake(block=block)

        subnet = {
                'name': self.netuid2subnet(netuid),
                'netuid': netuid,
                'stake': subnet_stake,
                'emission': subnet_emission,
                'n': n,
                'tempo': self.tempo( netuid = netuid , block=block),
                'immunity_period': self.immunity_period( netuid = netuid , block=block),
                'min_allowed_weights': self.min_allowed_weights( netuid = netuid, block=block ),
                'max_allowed_weights': self.max_allowed_weights( netuid = netuid , block=block),
                'max_allowed_uids': self.max_allowed_uids( netuid = netuid , block=block),
                'ratio': subnet_stake / total_stake,
                'founder': subnet_founder
            }

        return subnet
            
    subnet = subnet_state
    

    def get_total_subnets( self, block: Optional[int] = None ) -> int:
        return self.query( 'TotalSubnets', block=block ).value      
    
    def get_emission_value_by_subnet( self, netuid: int = None, block: Optional[int] = None ) -> Optional[float]:
        netuid = self.resolve_netuid( netuid )
        return Balance.from_nano( self.query( 'EmissionValues', block=block, params=[ netuid ] ).value )



    def is_registered( self, key: str, netuid: int = None, block: Optional[int] = None) -> bool:
        netuid = self.resolve_netuid( netuid )
        return bool(self.query('Uids', block=block, params=[ netuid, key ]).value)

    def get_uid_for_key_on_subnet( self, key_ss58: str, netuid: int, block: Optional[int] = None) -> int:
        return self.query( 'Uids', block=block, params=[ netuid, key_ss58 ] ).value  


    def emission( self, netuid: int = None, block: Optional[int] = None ) -> Optional[float]:
        netuid = self.resolve_netuid( netuid )
        return [submnet_emissions.value for submnet_emissions  in self.query_map('Emission',netuid, block=block ) ]

    def total_emission( self, netuid: int = None, block: Optional[int] = None ) -> Optional[float]:
        netuid = self.resolve_netuid( netuid )
        return sum(self.emission(netuid=netuid, block=block))


    def regblock(self, netuid: int = None, block: Optional[int] = None ) -> Optional[float]:
        netuid = self.resolve_netuid( netuid )
        return {k.value:v.value for k,v  in self.query_map('RegistrationBlock',params=netuid, block=block ) }


    def age(self, netuid: int = None) -> Optional[float]:
        netuid = self.resolve_netuid( netuid )
        regblock = self.regblock(netuid=netuid)
        block = self.block
        age = {}
        for k,v in regblock.items():
            age[k] = block - v
        return age



    def in_immunity(self, netuid: int = None ) -> Optional[float]:
        netuid = self.resolve_netuid( netuid )
        subnet = self.subnet(netuid=netuid)
        age = self.age(netuid=netuid)
        in_immunity = {}
        for k,v in age.items():
            in_immunity[k] = bool(v < subnet['immunity_period'])
        return in_immunity

    e = emission


    def stats(self, 
              search = None,
              netuid=None,  
              df:bool=True, 
              update:bool = False, 
              cols: list = ['name', 'address', 'registered', 'serving',  'emission', 'dividends', 'incentive', 'stake', 'balance'],
              **kwargs
              ):
        if update:
            self.sync()
        stats = []
        servers = c.servers(network='local')

        # keys = self.my_keys(netuid=netuid)
        my_modules = self.my_modules(netuid=netuid, fmt='j')
        module2stats = {}
        for module in my_modules:
            module['registered'] = True
            module2stats[module['name']] = module

        # add the servers tht are running that arent 
        for s in servers:
            if s not in module2stats:
                module2stats[s] = {**self.null_module, **{'name': s, 'registered': False}}

        stats = list(module2stats.values())
        for i in range(len(stats)):
            stats[i]['serving'] = bool(stats[i]['name'] in servers)
            for k in ['stake_to', 'stake_from']:
                if k in stats[i]:
                    stats[i][k] = {k: c.round_decimals(v, 2) for k,v in stats[i][k]}
            for k in ['balance', 'incentive', 'dividends', 'emission', 'stake']:
                if k in stats[i]:
                    stats[i][k] = c.round_decimals(stats[i][k], 4)

            stats[i]['my_stake'] = stats[i]['stake_to'].get(stats[i]['key'], 0)
        df_stats =  c.df(stats)
        # sort based on registered and balance

        df_stats = df_stats[cols]
    
        if len(df_stats) > 0:
            df_stats.sort_values(by=['registered', 'emission', 'stake'], ascending=False, inplace=True)

        if search is not None:
            df_stats = df_stats[df_stats['name'].str.contains(search, case=True)]
        if not df:
            return df_stats.to_dict('records')
        else:
            return df_stats
        
    def check_servers(self, search=None,  netuid=None):
        for m in c.stats(search=search, netuid=netuid, df=False):
            if m['serving'] == False and m['registered'] == True:
                c.register(m['name'])
            if m['serving'] == True and m['registered'] == False:
                self.register(m['name'])
                
    def key_stats(self, 
                key : str , 
                 netuid=None, 
                 fmt='j',
                 cols=[ 'stake_from', 'stake_to', 'stake'],
                **kwargs):
        
        key_stats = {}

        netuid = self.resolve_netuid(netuid)
        key_stats['balance'] = self.get_balance(key, fmt=fmt)


        key_stats['modules'] = {}
        for netuid in self.netuids():
            subnet_key_stats = {}
        
            module = self.key2module(key=key,netuid=netuid, fmt=fmt)
            register = bool(module.get('name', False))
            if register == False:
                continue
            if 'stake' in cols:
                subnet_key_stats['stake'] = module.get('stake', 0)
            if 'stake_to' in cols:
                subnet_key_stats['stake_to'] =  self.get_stake_to(key ,netuid=netuid, fmt=fmt)
            if 'stake_from' in cols:
                subnet_key_stats['stake_from'] =  module.get('stake_from', {})
            if 'incentive' in cols:
                subnet_key_stats['incentive'] = module.get('incentive', 0)
            if 'dividends' in cols:
                subnet_key_stats['dividends'] = module.get('dividends', 0)
            if 'emission' in cols:
                subnet_key_stats['emission'] = module.get('emission', 0)
            if 'registered' in cols:
                subnet_key_stats['registered'] = register
            if 'address' in cols:
                subnet_key_stats['address'] = module['key']
            key_stats['modules'] = subnet_key_stats
        return key_stats

        
    

        

    def get_current_block(self, network=None) -> int:
        r""" Returns the current block number on the chain.
        Returns:
            block_number (int):
                Current chain blocknumber.
        """     
        network = self.resolve_network(network)   
        with self.substrate as substrate:
            return substrate.get_block_number(None)


    def get_balance(self, key: str , block: int = None, fmt='j', network=None) -> Balance:
        r""" Returns the token balance for the passed ss58_address address
        Args:
            address (Substrate address format, default = 42):
                ss58 chain address.
        Return:
            balance (bittensor.utils.balance.Balance):
                account balance
        """
        network = self.resolve_network(network)
        key_ss58 = self.resolve_key_ss58( key )

        c.print(f"Getting balance for [bold white]{key_ss58}[/bold white] on network [bold white]{network}[/bold white].", verbose=True)
        
        try:
            @retry(delay=2, tries=3, backoff=2, max_delay=4)
            def make_substrate_call_with_retry():
                with self.substrate as substrate:
                    return substrate.query(
                        module='System',
                        storage_function='Account',
                        params=[key_ss58],
                        block_hash = None if block == None else substrate.get_block_hash( block )
                    )
            result = make_substrate_call_with_retry()
        except scalecodec.exceptions.RemainingScaleBytesNotEmptyException:
            c.critical("Your key it legacy formatted, you need to run btcli stake --ammount 0 to reformat it." )

        return  self.format_amount(result.value['data']['free'] , fmt=fmt)

    balance =  get_balance


    def get_balances(self,fmt:str = 'n', network = None, block: int = None, ) -> Dict[str, Balance]:
        
        network = self.resolve_network(network)
        @retry(delay=2, tries=3, backoff=2, max_delay=4)
        def make_substrate_call_with_retry():
            with self.substrate as substrate:
                return substrate.query_map(
                    module='System',
                    storage_function='Account',
                    block_hash = None if block == None else substrate.get_block_hash( block )
                )
        result = make_substrate_call_with_retry()
        return_dict = {}
        for r in result:
            bal = self.format_amount(int( r[1]['data']['free'].value ), fmt=fmt)
            return_dict[r[0].value] = bal
        return return_dict
    
    balances = get_balances
    
    def resolve_network(self, network: Optional[int] = None) -> int:
        if network == None:
            network = self.network
        if  not hasattr(self, 'substrate') and self.network == network:
            self.set_network(network)
            network =  self.network
        
        return network
    
    def resolve_subnet(self, subnet: Optional[int] = None) -> int:
        if isinstance(subnet, int):
            assert subnet in self.netuids()
            subnet = self.netuid2subnet(netuid=subnet)
        subnets = self.subnets()
        assert subnet in subnets, f"Subnet {subnet} not found in {subnets} for chain {self.chain}"
        return subnet

    @staticmethod
    def _null_module() -> ModuleInfo:
        module = ModuleInfo(
            uid = 0,
            netuid = 0,
            active =  0,
            stake = '0',
            rank = 0,
            emission = 0,
            incentive = 0,
            dividends = 0,
            last_update = 0,
            weights = [],
            bonds = [],
            is_null = True,
            key = "000000000000000000000000000000000000000000000000",
        )
        return module


    def subnets(self, **kwargs) -> Dict[int, str]:
        subnets = [s['name'] for s in self.subnet_states(**kwargs)]
        return subnets
    
    def netuids(self) -> Dict[int, str]:
        return sorted(list(self.subnet_namespace.values()))

    @property
    def subnet_namespace(self, network=network ) -> Dict[str, str]:
        records = self.query_map('SubnetNamespace')
        return {k.value:v.value for k,v in records}

    
    @property
    def subnet_reverse_namespace(self ) -> Dict[str, str]:
        
        return {v:k for k,v in self.subnet_namespace.items()}
    
    def netuid2subnet(self, netuid = None):
        subnet_reverse_namespace = self.subnet_reverse_namespace
        if netuid != None:
            return subnet_reverse_namespace.get(netuid, None)
        return subnet_reverse_namespace
    def subnet2netuid(self,subnet:str = None):
        subnet2netuid = self.subnet_namespace
        if subnet != None:
            return subnet2netuid.get(subnet, None)
        return subnet2netuid
        

    def resolve_netuid(self, netuid: int = None, namespace:dict=None) -> int:
        '''
        Resolves a netuid to a subnet name.
        '''
        if netuid == None:
            # If the netuid is not specified, use the default.
            netuid = self.netuid

        if isinstance(netuid, str):
            # If the netuid is a subnet name, resolve it to a netuid.
            if namespace == None:
                namespace = self.subnet_namespace
            assert netuid in namespace, f"Subnet {netuid} not found in {namespace} for chain {self.chain}"
            netuid = namespacenetuid
        elif isinstance(netuid, int):
            # If the netuid is an integer, ensure it is valid.
            assert netuid in self.netuids(), f"Netuid {netuid} not found in {self.netuids()} for chain {self.chain}"
            
        assert isinstance(netuid, int), "netuid must be an integer"
        return netuid
    
    resolve_net = resolve_subnet = resolve_netuid


    def key2name(self, key: str = None, netuid: int = None) -> str:
        modules = self.modules(netuid)
        key2name =  { m['key']: m['name']for m in modules}
        if key != None:
            return key2name[key]
            
        
    def name2key(self, name:str=None,  netuid: int = None) -> Dict[str, str]:
        # netuid = self.resolve_netuid(netuid)
             
        modules = self.modules(netuid=netuid)
        
        return { m['name']: m['key'] for m in modules}
        
    def is_unique_name(self, name: str, netuid=None):
        return bool(name not in self.namespace(netuid=netuid))


    def namespace(self, **kwargs) -> Dict[str, str]:
        
        modules = self.modules( **kwargs)
        namespace = { m['name']: m['address'] for m in modules}
        return namespace
    

        
    def servers(self, name=None, **kwargs) -> Dict[str, str]:
        servers = list(self.namespace( **kwargs).keys())

        if name != None:
            servers = [s for s in servers if name in s]
        return servers
        
        
    
    
    def name2uid(self, name: str = None, netuid: int = None) -> int:
        
        name2uid = { m['name']: m['uid'] for m in self.modules(netuid=netuid) }
        if name != None:
            return name2uid[name]
        return name2uid


    @property
    def block_time(self):
        return self.config.block_time


    def get_block(self, network=None, block_hash=None): 
        self.resolve_network(network)
        return self.substrate.get_block( block_hash=block_hash)

    def seconds_per_epoch(self, netuid=None, network=None):
        self.resolve_network(network)
        netuid =self.resolve_netuid(netuid)
        return self.block_time * self.subnet_state(netuid=netuid)['tempo']

    
    def get_module(self, name:str = None, key=None, netuid=None, **kwargs) -> ModuleInfo:
        if key != None:
            module = self.key2module(key=key, netuid=netuid, **kwargs)
        if name != None:
            module = self.name2module(name=name, netuid=netuid, **kwargs)
            
        return module

    @property
    def null_module(self):
        return {'name': None, 'key': None, 'uid': None, 'address': None, 'stake': 0, 'balance': 0, 'emission': 0, 'incentive': 0, 'dividends': 0, 'stake_to': {}, 'stake_from': {}, 'weight': []}
        
        
    def name2module(self, name:str = None, netuid: int = None, **kwargs) -> ModuleInfo:
        modules = self.modules(netuid=netuid, **kwargs)
        name2module = { m['name']: m for m in modules }
        default = {}
        if name != None:
            return name2module.get(name, self.null_module)
        return name2module
        
        
        
        
        
    def key2module(self, key: str = None, netuid: int = None, default: dict =None, **kwargs) -> Dict[str, str]:
        modules = self.modules(netuid=netuid, **kwargs)
        key2module =  { m['key']: m for m in modules }
        
        if key != None:
            key_ss58 = self.resolve_key_ss58(key)
            return  key2module.get(key_ss58, default if default != None else {})
        return key2module
        
    def module2key(self, module: str = None, **kwargs) -> Dict[str, str]:
        modules = self.modules(**kwargs)
        module2key =  { m['name']: m['key'] for m in modules }
        
        if module != None:
            return module2key[module]
        return module2key
    

    def module2stake(self,*args, **kwargs) -> Dict[str, str]:
        
        module2stake =  { m['name']: m['stake'] for m in self.modules(*args, **kwargs) }
        
        return module2stake
        

    
    
    def server_exists(self, module:str, netuid: int = None, **kwargs) -> bool:
        return bool(module in self.namespace(netuid=netuid, **kwargs))

    def default_module_info(self, **kwargs):
    
        
        module= {
                    'uid': -1,
                    'address': '0.0.0.0:1234',
                    'name': 'NA',
                    'key': 'NA',
                    'emission': 0,
                    'incentive': 0,
                    'dividends': 0,
                    'stake': 0,
                    'balance': 0,
                    
                }

        for k,v in kwargs.items():
            module[k] = v
        
        
        return module    
    # @c.timeit
    def modules(self,
                network = network,
                netuid: int = netuid,
                block: Optional[int] = None,
                fmt='nano', 
                keys = None,
                update: bool = False,
                include_weights = False,
                cache = True,
                df = False,
                ) -> Dict[str, ModuleInfo]:
        


        modules = []
        if cache:
            if netuid == None: 
                netuid = 0
            modules = self.state_dict(key='modules', network=network, update=update)[netuid]
    

        if len(modules) == 0:
            network = self.resolve_network(network)
            netuid = self.resolve_netuid(netuid)
            uid2addresses = { r[0].value: r[1].value for r in self.query_map('Address', netuid)}
            uid2key = { r[0].value: r[1].value for r in self.query_map('Keys', netuid)}
            uid2name = { r[0].value : r[1].value for r in self.query_map('Names', [netuid])}
            
            emission = self.emission(netuid=netuid, block=block)
            incentive = self.incentive(netuid=netuid, block=block)
            dividends = self.dividends(netuid=netuid, block=block)
            stake = self.stakes(netuid=netuid, block=block) # self.stake(netuid=netuid)
            stake_from = self.stake_from(netuid=netuid, block=block)
            stake_to = self.stake_to(netuid=netuid, block=block)
            regblock = self.regblock(netuid=netuid, block=block)
            balances = self.balances(block=block)
            
            if include_weights:
                weights = self.weights(netuid=netuid, block=block)
            
            for uid, address in uid2addresses.items():
                if uid not in uid2key:
                    c.error(f"Module {uid} has no key")
                    continue
                key = uid2key[uid]
                module= {
                    'uid': uid,
                    'address': address,
                    'name': uid2name[uid],
                    'key': key,
                    'emission': emission[uid],
                    'incentive': incentive[uid].value,
                    'dividends': dividends[uid].value,
                    'stake': stake.get(key, -1),
                    'balance': balances.get(key, 0),
                    'stake_from': stake_from.get(key, []),
                    'stake_to': stake_to.get(key, []),
                    'regblock': regblock.get(key, 0),
                }
                
                if include_weights:
                    if hasattr(weights[uid], 'value'):
                        
                        module['weight'] = weights[uid].value
                    elif isinstance(weights[uid], list):
                        module['weight'] = weights[uid]
                    else: 
                        raise Exception(f"Invalid weight for module {uid}")

                modules.append(module)
            


        if len(modules) > 0:
            if keys == None:
                keys = list(modules[0].keys())
            if isinstance(keys, str):
                keys = [keys]
            keys = list(set(keys))
            for i, module in enumerate(modules):
                modules[i] ={k: module[k] for k in keys}
 

                for k in ['balance', 'stake', 'emission']:
                    module[k] = self.format_amount(module[k], fmt=fmt)

                for k in ['incentive', 'dividends']:
                    if module[k] > 1:
                        module[k] = module[k] / (U16_MAX)
                module['stake_from']= [(k, self.format_amount(v, fmt=fmt))  for k, v in module['stake_from']]
                module['stake_to']= [(k, self.format_amount(v, fmt=fmt))  for k, v in module['stake_to']]
                modules[i] = module

        if df:
            modules = c.df(modules)

        return modules
        
    
      
    def names(self, netuid: int = None, **kwargs) -> List[str]:
        return list(self.namespace(netuid=netuid, **kwargs).keys())
    
    def my_modules(self, *args, **kwargs):
        my_modules = []
        address2key = c.address2key()
        for module in self.modules(*args, **kwargs):
            if module['key'] in address2key:
                my_modules += [module]
        return my_modules
    
    def my_modules_names(self, *args, **kwargs):
        my_modules = self.my_modules(*args, **kwargs)
        return [m['name'] for m in my_modules]

    def my_module_keys(self, *args,  **kwargs):
        modules = self.my_modules(*args, **kwargs)
        return [m['key'] for m in modules]

    def my_keys(self, *args, mode='all' , **kwargs):

        modules = self.my_modules(*args,**kwargs)
        address2module = {m['key']: m for m in modules}
        address2balances = self.balances()
        keys = []
        address2key = c.address2key()
        for address, key in address2key.items():
            
            if mode == 'live' and (address in address2module):
                keys += [key]
            elif mode == 'dead' and (address not in address2module and address in address2balances):
                keys += [key]
            elif mode == 'all' and (address in address2module or address in address2balances):
                keys += [key]
            
        return keys

    @classmethod
    def kill_chain(cls, chain=chain):
        cls.kill_nodes(chain=chain)
        cls.refresh_chain_info(chain=chain)

    @classmethod
    def refresh_chain_info(cls, chain=chain):
        cls.putc(f'chain_info.{chain}', {'nodes': {}, 'boot_nodes': []})
    @classmethod
    def kill_nodes(cls, chain=chain, verbose=True):
        for node_path in cls.live_nodes(chain=chain):
            if verbose:
                c.print(f'killing {node_path}',color='red')
            c.pm2_kill(node_path)

        return cls.live_nodes(chain=chain)
    
    def query(self, name,  params, block=None,  network: str = network,):
        if not isinstance(params, list):
            params = [params]
        self.resolve_network(network)
        with self.substrate as substrate:
            value =  substrate.query(
                module='SubspaceModule',
                storage_function = name,
                block_hash = None if block == None else substrate.get_block_hash(block), 
                params = params
            )
            
        return value
        
    @classmethod
    def test(cls, network=subnet):
        subspace = cls()        
        for key_path, key in c.get_keys('test').items():
            port  = c.free_port()
            subspace.register(key=key, 
                              network=network,
                              address=f'{c.external_ip()}:{port}', 
                              name=f'module{key_path}')

    @classmethod
    def test_balance(cls):
        self = cls()
        key = cls.get_key('//Alice')
        c.print(self.get_balance(key.ss58_address))
        
        key2 = cls.get_key('//Bob')
        
        self.transfer(key=key, dest=key2.ss58_address, amount=10)
        
        c.print(self.get_balance(key2.ss58_address))
        
    
    @classmethod
    def test_chain(cls, chain:str = chain, verbose:bool=True, snap:bool=False ):

        cls.cmd('cargo test', cwd=cls.chain_path, verbose=verbose)
        cls.build_spec(chain, snap=snap)    
        

    @classmethod
    def gen_key(cls, *args, **kwargs):
        return c.module('key').gen(*args, **kwargs)
    

    def keys(self, netuid = None, **kwargs):
        netuid = self.resolve_netuid(netuid)
        return [m['key'] for m in self.modules(netuid=netuid, **kwargs)]
    
    def registered_keys(self, netuid = None, **kwargs):
        keys = self.keys(netuid=netuid, **kwargs)
        address2key = c.address2key()
        registered_keys = []
        for k_addr in keys:
            if k_addr in address2key:
                registered_keys += [address2key[k_addr]]
        return registered_keys

    def registered_servers(self, netuid = None, network = network,  **kwargs):
        netuid = self.resolve_netuid(netuid)
        network = self.resolve_network(network)
        servers = c.servers(network='local')
        registered_keys = []
        for s in servers:
            if self.is_registered(s, netuid=netuid):
                registered_keys += [s]
        return registered_keys
    reged = reged_servers = registered_servers

    def unregistered_servers(self, netuid = None, network = network,  **kwargs):
        netuid = self.resolve_netuid(netuid)
        network = self.resolve_network(network)
        network = self.resolve_network(network)
        servers = c.servers(network='local')
        unregistered_keys = []
        for s in servers:
            if not self.is_registered(s, netuid=netuid):
                unregistered_keys += [s]
        return unregistered_keys

    
    def check_reged(self, netuid = None, network = network,  **kwargs):
        reged = self.reged(netuid=netuid, network=network, **kwargs)
        jobs = []
        for module in reged:
            job = c.call(module=module, fn='info',  network='subspace', netuid=netuid, return_future=True)
            jobs += [job]

        results = dict(zip(reged, c.gather(jobs)))

        return results 


    
    unreged = unreged_servers = unregistered_servers
                
    def most_valuable_key(self, netuid = None, **kwargs):
        modules = self.my_modules(netuid=netuid, **kwargs)
        most_valuable_value = 0
        most_valuable_key = None
        address2key = c.address2key()
        for m in modules:
            value = m['stake'] + m['balance']
            if value > most_valuable_value:
                most_valuable_value  = value
                most_valuable_key = address2key[m['key']]
        return most_valuable_key

    def most_staked_key(self, netuid = None,  **kwargs):
        modules = self.my_modules(netuid=netuid, **kwargs)
        most_staked_value = 0
        most_staked_key = None
        address2key = c.address2key()
        for m in modules:
            if m['stake'] > most_staked_value:
                most_staked_value = m['stake']
                most_staked_key = address2key[m['key']]
        return most_staked_key

    reged = registered_keys
    
    def weights(self, netuid = None, **kwargs) -> list:
        netuid = self.resolve_netuid(netuid)
        subnet_weights =  self.query_map('Weights', netuid, **kwargs)
        weights = {uid.value:list(map(list, w.value)) for uid, w in subnet_weights if w != None and uid != None}
        uids = self.uids(netuid=netuid, **kwargs)
        weights = {uid: weights[uid] if uid in weights else [] for uid in uids}

        return {uid: len(w) for uid, w in weights.items() if len(w) > 0}
            
        
    def regprefix(self, prefix, netuid = None, network=None, **kwargs):
        network = self.resolve_network(network)
        netuid = self.resolve_netuid(netuid)
        c.servers(network=network, prefix=prefix)
        
    
    def emission(self, netuid = netuid, network=None, **kwargs):
        return [v.value for v in self.query('Emission', params=[netuid], network=network, **kwargs)]
        
    def incentive(self, netuid = netuid, block=None,   network=network, **kwargs):
        return self.query('Incentive', params=netuid, network=network, block=block, **kwargs)
        
    
    def dividends(self, netuid = netuid, network=None, **kwargs):
        return self.query('Dividends', params=netuid, network=network,  **kwargs)

    def uids(self, netuid: int = None, reverse: bool =False , **kwargs):
        netuid = self.resolve_netuid(netuid)
        return sorted([v[1].value for v in self.query_map('Uids' ,netuid )], reverse=reverse)

    def uid2key(self, network:str=None, netuid:int = None, **kwargs):
        network = self.resolve_network(network)
        netuid = self.resolve_netuid(netuid)
        
        keys = self.query_map('Keys', netuid, **kwargs)
        return {k.value:v.value for k, v in keys if k != None and v != None}


    def registration_blocks(self, netuid: int = None, network:str=  None, **kwargs):
        network = self.resolve_network(network)
        netuid = self.resolve_netuid(netuid)
        
        registration_blocks = self.query_map('RegistrationBlock', netuid, **kwargs)
        return {k.value:v.value for k, v in registration_blocks if k != None and v != None}
    
    
    
    
    def key2uid(self, network:str=  None,netuid: int = None, **kwargs):
        return {v:k for k,v in self.uid2key(network=network, netuid=netuid, **kwargs).items()}


    @classmethod
    def get_node_id(cls,  node='alice',
                    chain=chain, 
                    max_trials=10, 
                    sleep_interval=1,
                     mode=mode, 
                     verbose=True
                     ):
        node2path = cls.node2path(chain=chain)
        node_path = node2path[node]
        node_id = None
        node_logs = ''
        indicator = 'Local node identity is: '

        while indicator not in node_logs and max_trials > 0:
            if mode == 'docker':
                node_path = node2path[node]
                node_logs = c.module('docker').logs(node_path)
            elif mode == 'local':
                node_logs = c.logs(node_path, start_line = 0 , end_line=400, mode='local')
            else:
                raise Exception(f'Invalid mode {mode}')

            if indicator in node_logs:
                break
            max_trials -= 1
            c.sleep(sleep_interval)
        for line in node_logs.split('\n'):
            # c.print(line)
            if 'Local node identity is: ' in line:
                node_id = line.split('Local node identity is: ')[1].strip()
                break

        if node_id == None:
            raise Exception(f'Could not find node_id for {node} on {chain}')

        return node_id
        
        
    @classmethod
    def node_help(cls, mode=mode):
        chain_release_path = cls.chain_release_path(mode=mode)
        cmd = f'{chain_release_path} --help'
        if mode == 'docker':
            cmd = f'docker run subspace {cmd}'
        elif mode == 'local':
            cmd = f'{cmd}'

        c.cmd(cmd, verbose=True)  

 

    def get_archive_blockchain_archives(self, netuid=netuid, network:str=network, **kwargs) -> List[str]:

        datetime2archive =  self.datetime2archive(network=network, **kwargs) 
        break_points = []
        last_block = 10e9
        blockchain_id = 0
        get_archive_blockchain_ids = []
        for dt, archive_path in enumerate(datetime2archive):
            
            archive_block = int(archive_path.split('block-')[-1].split('-')[0])
            if archive_block < last_block :
                break_points += [archive_block]
                blockchain_id += 1
            last_block = archive_block
            get_archive_blockchain_ids += [{'blockchain_id': blockchain_id, 'archive_path': archive_path, 'block': archive_block}]

            c.print(archive_block, archive_path)

        return get_archive_blockchain_ids



    def get_archive_blockchain_info(self, netuid=netuid, network:str=network, **kwargs) -> List[str]:

        datetime2archive =  self.datetime2archive(network=network, **kwargs) 
        break_points = []
        last_block = 10e9
        blockchain_id = 0
        get_archive_blockchain_info = []
        for i, (dt, archive_path) in enumerate(datetime2archive.items()):
            c.print(archive_path)
            archive_block = int(archive_path.split('block-')[-1].split('-time')[0])
            
            c.print(archive_block < last_block, archive_block, last_block)
            if archive_block < last_block :
                break_points += [archive_block]
                blockchain_id += 1
                blockchain_info = {'blockchain_id': blockchain_id, 'archive_path': archive_path, 'block': archive_block, 'earliest_block': archive_block}
                get_archive_blockchain_info.append(blockchain_info)
                c.print(archive_block, archive_path)
            last_block = archive_block
            if len(break_points) == 0:
                continue


        return get_archive_blockchain_info


    


            

    @classmethod
    def most_recent_archives(cls,):
        archives = cls.search_archives()
        return archives
    
    @classmethod
    def num_archives(cls, *args, **kwargs):
        return len(cls.datetime2archive(*args, **kwargs))

    @classmethod
    def search_archives(cls, 
                    lookback_hours : int = 10,
                    end_time :str = 'now', 
                    start_time: Optional[Union[int, str]] = None, 
                    netuid=0, 
                    n = 1000,
                    **kwargs):


        if end_time == 'now':
            end_time = c.time()
        elif isinstance(end_time, str):
            c.print(end_time)
            
            end_time = c.datetime2time(end_time)
        elif isinstance(end_time, int):
            pass
        else:
            raise Exception(f'Invalid end_time {end_time}')
            end_time = c.time2datetime(end_time)



        if start_time == None:
            start_time = end_time - lookback_hours*3600
            start_time = c.time2datetime(start_time)

        if isinstance(start_time, int) or isinstance(start_time, float):
            start_time = c.time2datetime(start_time)
        
        if isinstance(end_time, int) or isinstance(end_time, float):
            end_time = c.time2datetime(end_time)
        

        assert end_time > start_time, f'end_time {end_time} must be greater than start_time {start_time}'
        datetime2archive = cls.datetime2archive()
        datetime2archive= {k: v for k,v in datetime2archive.items() if k >= start_time and k <= end_time}
        c.print(len(datetime2archive))
        factor = len(datetime2archive)//n
        if factor == 0:
            factor = 1
        archives = []

        c.print('Searching archives from', start_time, 'to', end_time)

        cnt = 0
        for i, (archive_dt, archive_path) in enumerate(datetime2archive.items()):
            if i % factor != 0:
                continue
            archive_block = int(archive_path.split('block-')[-1].split('-time')[0])
            archive = c.get(archive_path)
            total_balances = sum([b for b in archive['balances'].values()])
            # st.write(archive['modules']netuid[:3])
            total_stake = sum([sum([_[1]for _ in m['stake_from']]) for m in archive['modules'][netuid]])
            subnet = archive['subnets'][netuid]
            row = {
                    'block': archive_block,  
                    'total_stake': total_stake*1e-9,
                    'total_balance': total_balances*1e-9, 
                    'market_cap': (total_stake+total_balances)*1e-9 , 
                    'dt': archive_dt, 
                    'block': archive['block'], 
                    'path': archive_path, 
                    'mcap_per_block': 0,
                }
            
            if len(archives) > 0:
                denominator = ((row['block']//subnet['tempo']) - (archives[-1]['block']//subnet['tempo']))*subnet['tempo']
                if denominator > 0:
                    row['mcap_per_block'] = (row['market_cap'] - archives[-1]['market_cap'])/denominator

            archives += [row]
            
        return archives

    @classmethod
    def archive_history(cls, *args, 
                     network=network, 
                     netuid= 0 , update=True,  **kwargs):
        path = f'history/{network}.{netuid}.json'

        archive_history = []
        if not update:
            archive_history = cls.get(path, [])
        if len(archive_history) == 0:
            archive_history =  cls.search_archives(*args,network=network, netuid=netuid, **kwargs)
            cls.put(path, archive_history)
            
        
        return archive_history
        

        

        
        
        

    @classmethod
    def dashboard(cls):
        import streamlit as st
        block = 7014
        netuid = 0
        c.module('subspace.dashboard').dashboard()
        


    @classmethod
    def st_search_archives(cls,
                        start_time = '2023-09-08 04:00:00', 
                        end_time = '2023-09-08 04:30:00'):
        start_time = st.text_input('start_time', start_time)
        end_time = st.text_input('end_time', end_time)
        df = cls.search_archives(end_time=end_time, start_time=start_time)

        
        st.write(df)

    
    @classmethod
    def build_snapshot(cls, 
              path : str ,
             network : str =network,
             subnet_params : List[str] =  ['name', 'tempo', 'immunity_period', 'min_allowed_weights', 'max_allowed_weights', 'max_allowed_uids', 'founder'],
            module_params : List[str] = ['key', 'name', 'address'],
            save: bool = True, 
            min_balance:int = 100000,
            verbose: bool = False,
             **kwargs):
        
        state = cls.get(path)
        
        snap = {
                        'subnets' : [[s[p] for p in subnet_params] for s in state['subnets']],
                        'modules' : [[[m[p] for p in module_params] for m in modules ] for modules in state['modules']],
                        'balances': {k:v for k,v in state['balances'].items() if v > min_balance},
                        'stake_to': [[[staking_key, stake_to] for staking_key,stake_to in state['stake_to'][i].items()] for i in range(len(state['subnets']))],
                        'block': state['block'],
                        }
                        
        # add weights if not already in module params
        if 'weights' not in module_params:
            snap['modules'] = [[m + c.copy([[]]) for m in modules] for modules in snap['modules']]
        
        # save snapshot into subspace/snapshots/{network}.json
        if save:
            snap_dir = f'{cls.chain_path}/snapshots'
            c.mkdir(snap_dir)
            snap_path = f'{snap_dir}/{network}.json'
            c.print('Saving snapshot to', snap_path, verbose=verbose)
            c.put_json(snap_path, snap)
        # c.print(snap['modules'][0][0])
        
        return {'success': True, 'msg': f'Saved snapshot to {snap_path} from {path}'}    
    
    
    
    @classmethod
    def check(cls, netuid=0):
        self = cls()

        # c.print(len(self.modules()))
        c.print(len(self.query_map('Keys', netuid)), 'keys')
        c.print(len(self.query_map('Names', netuid)), 'names')
        c.print(len(self.query_map('Address', netuid)), 'address')
        c.print(len(self.incentive()), 'incentive')
        c.print(len(self.uids()), 'uids')
        c.print(len(self.stakes()), 'stake')
        c.print(len(self.query_map('Emission')[0][1].value), 'emission')
        c.print(len(self.query_map('Weights', netuid)), 'weights')

    def vote_pool(self, netuid=None, network=None):
        my_modules = self.my_modules(netuid=netuid, network=network, names_only=True)
        for m in my_modules:
            c.vote(m, netuid=netuid, network=network)
        return {'success': True, 'msg': f'Voted for all modules {my_modules}'}


    
    @classmethod
    def snapshots(cls):
        return list(cls.snapshot_map().keys())

    @classmethod
    def snapshot_map(cls):
        return {l.split('/')[-1].split('.')[0]: l for l in c.ls(f'{cls.chain_path}/snapshots')}
        
    @classmethod
    def get_snapshot(cls, chain=chain):
        return c.get_json(cls.snapshot_map()[chain])

    def update_snapshot(cls, chain=chain):
        snapshot = cls.get_snapshot(chain=chain)
        version = snapshot.get('version', 0)
        if version == 0:
            # version 0 does not have weights
            max_allowed_weights = 100
            snapshot['subnets'] = [[*s[:4], max_allowed_weights ,*s[4:]] for s in snapshot['subnets']]
    @classmethod
    def install_rust(cls, sudo=True):
        c.cmd(f'chmod +x scripts/install_rust_env.sh',  cwd=cls.chain_path, sudo=sudo)

        
    

    @classmethod
    def build(cls, chain:str = chain, 
             build_spec:bool=True, 
             build_runtime:bool=True,
             build_snapshot:bool=False,  
             verbose:bool=True, 
             mode = mode

             ):

            
        if build_runtime:
            cls.build_runtime(verbose=verbose , mode=mode)

        if build_snapshot:
            cls.build_snapshot(chain=chain, verbose=verbose)

        if build_spec:
            cls.build_spec(chain=chain, verbose=verbose, mode=mode)


    @classmethod
    def prune_node_keys(cls, max_valis:int=6, chain=chain):

        keys = c.keys(f'subspace.node.{chain}.vali')
        rm_keys = []
        for key in keys:
            if int(key.split('.')[-2].split('_')[-1]) > max_valis:
                rm_keys += [key]
        for key in rm_keys:
            c.rm_key(key)
        return rm_keys
        
        
    @classmethod
    def add_node_keys(cls,  valis:int=24, nonvalis:int=16, chain:str=chain, refresh:bool=False ):
        for i in range(valis):
            cls.add_node_key(node=i,  mode='vali', chain=chain, refresh=refresh)
        for i in range(nonvalis):
            cls.add_node_key(node=i,  mode='nonvali' , chain=chain, refresh=refresh)

    def num_vali_keys(self, chain=chain):
        return len(self.vali_node_keys(chain=chain))

    @classmethod
    def num_node_keys(cls, mode='all', chain=chain):
        if mode == 'vali':
            keys = cls.vali_node_keys(chain=chain)
        elif mode == 'nonvali':
            keys = cls.nonvali_node_keys(chain=chain)
        elif mode == 'all':
            keys = cls.node_keys(chain=chain)
        else:
            raise ValueError(f'Unknown mode {mode}, must be one of vali, nonvali, all')

        return len(keys)

    node_key_prefix = 'subspace.node'
    
    @classmethod
    def rm_node_keys(cls,chain=chain):
        for key in cls.node_key_paths(chain=chain):
            c.print(f'removing node key {key}')
            c.rm_key(key)
        return {'success':True, 'message':'removed all node keys', 'chain':chain, 'keys_left':cls.node_keys(chain=chain)}
    
    @classmethod
    def vali_node_key2address(cls,chain=chain):
        key2address =  c.key2address(f'{cls.node_key_prefix}.{chain}')
        return key2address
    @classmethod
    def resolve_node_key_path(cls, node='alice', mode='vali',chain=chain, tag_seperator='_'):
        return f'{cls.node_key_prefix}.{chain}.{mode}{tag_seperator}{node}'

    @classmethod
    def random_node_key(cls, mode='vali', chain=chain):
        return c.choice(cls.node_keys(mode=mode, chain=chain))

    @classmethod
    def resolve_node_key(cls, node=None, mode='vali', chain=chain):
        if node == None:
            cls.vali_node_keys(chain)
        
        return 

    @classmethod
    def get_node_key(cls, node='alice', chain=chain, mode='vali'):
        if not cls.node_exists(node=node, chain=chain, mode=mode):
            cls.add_node_key(node=node, vali=vali, chain=chain)
        
        key_path = cls.resolve_node_key_path(node=node, mode=mode, chain=chain)
        keys = c.keys(key_path)
        return keys
    
    @classmethod
    def node_key_paths(cls, node='alice', chain=chain, mode='all'):
        if mode == 'all':
            return c.keys(f'{cls.node_key_prefix}.{chain}') 
        elif mode in ['nonvali', 'vali']:
            return c.keys(f'{cls.node_key_prefix}.{chain}.{mode}')
    

    @classmethod
    def node_keys(cls,chain=chain, mode = 'all'):
        vali_node_keys = {}
        for key_name in c.keys(f'{cls.node_key_prefix}.{chain}'):
            name = key_name.split('.')[-2]
            role = key_name.split('.')[-1]
            key = c.get_key(key_name)
            if name not in vali_node_keys:
                vali_node_keys[name] = { }
            vali_node_keys[name][role] =  key.ss58_address
        return vali_node_keys

    @classmethod
    def node_key_info_map(cls,chain=chain, mode = 'all'):
        keys = cls.node_keys(chain=chain, mode=mode)
        return {k:c.key_info(k) for k in keys}

    @classmethod
    def nodes(cls, mode='all', chain=chain):
        nodes = list(cls.node_keys(chain=chain).keys())
        if mode == 'vali':
            nodes = [n for n in nodes if n.startswith('vali')]
        elif mode == 'nonvali':
            nodes = [n for n in nodes if n.startswith('nonvali')]
        elif mode == 'all':
            pass
        else:
            raise ValueError(f'Unknown mode {mode}, must be one of vali, nonvali, all')

        return nodes

    @classmethod
    def vali_nodes(cls, chain=chain):
        return cls.nodes(mode='vali', chain=chain)

    @classmethod
    def nonvali_nodes(cls, chain=chain):
        return cls.nodes(mode='nonvali', chain=chain)

    @classmethod
    def vali_node_keys(cls,chain=chain):
        return {k:v for k,v in  cls.node_keys(chain=chain).items() if k.startswith('vali')}
    
    @classmethod
    def nonvali_node_keys(self,chain=chain):
        return {k:v for k,v in  self.node_keys(chain=chain).items() if k.startswith('nonvali')}
    

    @classmethod
    def node_key_exists(cls, node='alice', chain=chain):
        return len(cls.node_key_paths(node=node, chain=chain)) > 0

    @classmethod
    def add_node_key(cls,
                     node:str,
                     mode: str = 'nonvali',
                     chain = chain,
                     tag_seperator = '_', 
                     refresh: bool = False,
                     ):
        '''
        adds a node key
        '''
        cmds = []

        assert mode in ['vali', 'nonvali'], f'Unknown mode {mode}, must be one of vali, nonvali'
        node = str(node)

        c.print(f'adding node key {node} for chain {chain}')

        node = c.copy(f'{mode}{tag_seperator}{node}')


        chain_path = cls.chain_release_path(mode='local')

        for key_type in ['gran', 'aura']:

            if key_type == 'gran':
                schema = 'Ed25519'
            elif key_type == 'aura':
                schema = 'Sr25519'

            key_path = f'{cls.node_key_prefix}.{chain}.{node}.{key_type}'

            key = c.get_key(key_path,crypto_type=schema, refresh=refresh)

            base_path = cls.resolve_base_path(node=node, chain=chain)

            
            cmd  = f'''{chain_path} key insert --base-path {base_path} --chain {chain} --scheme {schema} --suri "{key.mnemonic}" --key-type {key_type}'''
            
            cmds.append(cmd)

        for cmd in cmds:
            # c.print(cmd)
            # volumes = f'-v {base_path}:{base_path}'
            # c.cmd(f'docker run {volumes} subspace {cmd} ', verbose=True)
            c.cmd(cmd, verbose=True, cwd=cls.chain_path)

        return {'success':True, 'node':node, 'chain':chain, 'keys':cls.get_node_key(node=node, chain=chain, mode=mode)}



    @classmethod   
    def purge_chain(cls,
                    base_path:str = None,
                    chain:str = chain,
                    node:str = 'alice',
                    sudo = False):
        if base_path == None:
            base_path = cls.resolve_base_path(node=node, chain=chain)
        
        return c.rm(base_path+'/chains/commune/db')
    
    


    @classmethod
    def chain_target_path(self, chain:str = chain):
        return f'{self.chain_path}/target/release/node-subspace'

    @classmethod
    def build_runtime(cls, verbose:bool=True, mode=mode):
        if mode == 'docker':
            c.module('docker').build(cls.chain_name)
        elif mode == 'local':
            c.cmd('cargo build --release --locked', cwd=cls.chain_path, verbose=verbose)
        else:
            raise ValueError(f'Unknown mode {mode}, must be one of docker, local')

    @classmethod
    def chain_release_path(cls, mode='local'):

        if mode == 'docker':
            chain_path = f'/subspace'
        elif mode == 'local':
            chain_path = cls.chain_path
        else:
            raise ValueError(f'Unknown mode {mode}, must be one of docker, local')
        path =   f'{chain_path}/target/release/node-subspace'
        return path

    @classmethod
    def resolve_base_path(cls, node='alice', chain=chain):
        return cls.resolve_path(f'nodes/{chain}/{node}')
    
    @classmethod
    def resolve_node_keystore_path(cls, node='alice', chain=chain):
        path =  cls.resolve_base_path(node=node, chain=chain) + f'/chains/commune/keystore'
        if not c.exists(path):
            c.mkdir(path)
        return path

    @classmethod
    def build_spec(cls,
                   chain = chain,
                   disable_default_bootnode: bool = True,
                   snap:bool = False,
                   verbose:bool = True,
                   vali_node_keys:dict = None,
                   mode = mode,
                   ):

        if snap:
            cls.snap()

        chain_spec_path = cls.chain_spec_path(chain)
        chain_release_path = cls.chain_release_path(mode=mode)

        cmd = f'{chain_release_path} build-spec --chain {chain}'
        
        if disable_default_bootnode:
            cmd += ' --disable-default-bootnode'  
        cmd += f' > {chain_spec_path}'
        
        # chain_spec_path_dir = os.path.dirname(chain_spec_path)
        c.print(cmd)
        if mode == 'docker':
            volumes = f'-v {cls.spec_path}:{cls.spec_path}'
            c.cmd(f'docker run {volumes} subspace bash -c "{cmd}"')
        elif mode == 'local':
            c.cmd(f'bash -c "{cmd}"', cwd=cls.chain_path, verbose=True)    


        # ADD THE VALI NODE KEYS

        if vali_node_keys == None:
            vali_node_keys = cls.vali_node_keys(chain=chain)
        spec = c.get_json(chain_spec_path)
        spec['genesis']['runtime']['aura']['authorities'] = [k['aura'] for k in vali_node_keys.values()]
        spec['genesis']['runtime']['grandpa']['authorities'] = [[k['gran'],1] for k in vali_node_keys.values()]
        c.put_json(chain_spec_path, spec)
        resp = {'spec_path': chain_spec_path, 'spec': spec}
        return {'success':True, 'message':'built spec', 'chain':chain}


    @classmethod
    def chain_specs(cls):
        return c.ls(f'{cls.spec_path}/')
    
    @classmethod
    def chain2spec(cls, chain = None):
        chain2spec = {os.path.basename(spec).replace('.json', ''): spec for spec in cls.specs()}
        if chain != None: 
            return chain2spec[chain]
        return chain2spec
    
    specs = chain_specs
    @classmethod
    def get_spec(cls, chain:str=chain):
        chain = cls.chain_spec_path(chain)
        
        return c.get_json(chain)

    @classmethod
    def spec_exists(cls, chain):
        return c.exists(f'{cls.spec_path}/{chain}.json')



    @classmethod
    def chain_spec_path(cls, chain = None):
        if chain == None:
            chain = cls.network
        return cls.spec_path + f'/{chain}.json'
        
    @classmethod
    def new_chain_spec(self, 
                       chain,
                       base_chain:str = chain, 
                       balances : 'List[str, int]' = None,
                       aura_authorities: 'List[str, int]' = None,
                       grandpa_authorities: 'List[str, int]' = None,
                       ):
        base_spec =  self.get_spec(base_chain)
        new_chain_path = f'{self.spec_path}/{chain}.json'
        
        if balances != None:
            base_spec['balances'] = balances
        if aura_authorities != None:
            base_spec['balances'] = aura_authorities
        c.put_json( new_chain_path, base_spec)
        
        return base_spec
    
    new_chain = new_chain_spec

    @classmethod
    def rm_chain(self, chain):
        return c.rm(self.chain_spec_path(chain))
    
    @classmethod
    def insert_node_key(cls,
                   node='node01',
                   chain = 'jaketensor_raw.json',
                   suri = 'verify kiss say rigid promote level blue oblige window brave rough duty',
                   key_type = 'gran',
                   scheme = 'Sr25519',
                   password_interactive = False,
                   ):
        
        chain_spec_path = cls.chain_spec_path(chain)
        node_path = f'/tmp/{node}'
        
        if key_type == 'aura':
            schmea = 'Sr25519'
        elif key_type == 'gran':
            schmea = 'Ed25519'
        
        if not c.exists(node_path):
            c.mkdir(node_path)

        cmd = f'{cls.chain_release_path()} key insert --base-path {node_path}'
        cmd += f' --suri "{suri}"'
        cmd += f' --scheme {scheme}'
        cmd += f' --chain {chain_spec_path}'

        key_types = ['aura', 'gran']

        assert key_type in key_types, f'key_type ({key_type})must be in {key_types}'
        cmd += f' --key-type {key_type}'
        if password_interactive:
            cmd += ' --password-interactive'
        
        c.print(cmd, color='green')
        return c.cmd(cmd, cwd=cls.chain_path, verbose=True)
    
    @classmethod
    def insert_node_keys(cls,
                   aura_suri : str, 
                   grandpa_suri :str,
                    node='node01',
                   password_interactive = False,
                   ):
        '''
        Insert aura and gran keys for a node
        '''
        cls.insert_node_key(node=node, key_type='aura',  suri=aura_suri)
        cls.insert_node_key(node=node, key_type='gran', suri=grandpa_suri)
       
        return c.cmd(cmd, cwd=cls.chain_path, verbose=True)
    
    
    @classmethod
    def live_nodes(cls, chain=chain, mode=mode):
        prefix = f'{cls.node_prefix()}.{chain}'
        if mode == 'local':
            nodes =  c.pm2ls(prefix)
        else:
            nodes =  c.module('docker').ps(prefix)

        return nodes
    @classmethod
    def node2path(cls, chain=chain, mode = mode):
        prefix = f'{cls.node_prefix()}.{chain}'
        if mode == 'docker':
            path = prefix
            nodes =  c.module('docker').ps(path)
            return {n.split('.')[-1]: n for n in nodes}
        elif mode == 'local':
        
            nodes =  c.pm2ls(f'{prefix}')
            return {n.split('.')[-1]: n for n in nodes}
    @classmethod
    def nonvalis(cls, chain=chain):
        chain_info = cls.chain_info(chain=chain)
        return [node_info['node'] for node_info in chain_info['nodes'].values() if node_info['validator'] == False]

    @classmethod
    def valis(cls, chain=chain):
        chain_info = cls.chain_info(chain=chain)
        c.print(chain_info.keys())
        return [node_info['node'] for node_info in chain_info['nodes'].values() if node_info['validator'] == True]

    @classmethod
    def num_valis(cls, chain=chain):
        return len(cls.vali_nodes(chain=chain))


    @classmethod
    def node_prefix(cls, chain=chain):
        return f'{cls.module_path()}.node'
    


    @classmethod
    def chain_info(cls, chain=chain, default:dict=None ): 
        default = {} if default == None else default
        return cls.getc(f'chain_info.{chain}', default)


    @classmethod
    def node_info(cls, node='alice', chain=chain): 
        return cls.getc(f'chain_info.{chain}.{node}')

    @classmethod
    def has_node(cls, node='alice', chain=chain):
        return node in cls.nodes(chain=chain)

    @classmethod
    def is_vali_node(cls, node='alice', chain=chain):
        node_info = cls.node_info(node=node, chain=chain)
        if node_info == None:
            return False
        assert 'validator' in node_info, f'node_info for {node} on {chain} does not have a validator key'
        return node_info['validator']

    @classmethod
    def rm_node(cls, node='bobby',  chain=chain): 
        cls.rmc(f'chain_info.{chain}.{node}')
        return {'success':True, 'msg': f'removed node_info for {node} on {chain}'}


    @classmethod
    def rm_nodes(cls, node='bobby',  chain=chain): 
        cls.rmc(f'chain_info.{chain}.{node}')
        return {'success':True, 'msg': f'removed node_info for {node} on {chain}'}


    @classmethod
    def get_boot_nodes(cls, chain=chain):
        return cls.getc('chain_info.{chain}.boot_nodes')

    @classmethod
    def start_nodes(self, node='node', n=10, chain=chain, **kwargs):
        nodes = self.nodes(chain=chain)
        for node in nodes:
            self.start_node(node=node, chain=chain, **kwargs)




    @classmethod
    def start_node(cls,
                 node : str,
                 chain:int = network,
                 port:int=None,
                 rpc_port:int=None,
                 ws_port:int=None,
                 telemetry_url:str = 'wss://telemetry.gpolkadot.io/submit/0',
                 purge_chain:bool = True,
                 refresh:bool = False,
                 verbose:bool = False,
                 boot_nodes = None,
                 node_key = None,
                 mode :str = mode,
                 rpc_cors = 'all',
                 validator:bool = False,
                 
                 ):

        ip = c.ip()

        node_info = c.locals2kwargs(locals())

        cmd = cls.chain_release_path()

        free_ports = c.free_ports(n=3)

        if port == None:
            node_info['port'] = port = free_ports[0]
            
        if rpc_port == None:
            node_info['rpc_port'] = rpc_port = free_ports[1]
        if ws_port == None:
            node_info['ws_port'] = ws_port = free_ports[2]
        # resolve base path
        base_path = cls.resolve_base_path(node=node, chain=chain)
        
        # purge chain
        if purge_chain:
            cls.purge_chain(base_path=base_path)
            
        cmd_kwargs = f' --base-path {base_path}'

        chain_spec_path = cls.chain_spec_path(chain)
        cmd_kwargs += f' --chain {chain_spec_path}'
    
            
        if validator :
            cmd_kwargs += ' --validator'
        else:
            cmd_kwargs += ' --ws-external --rpc-external'
        cmd_kwargs += f' --port {port} --rpc-port {rpc_port} --ws-port {ws_port}'
        
        chain_info = cls.getc(f'chain_info.{chain}', {})
        boot_nodes = chain_info.get('boot_nodes', [])
        chain_info['nodes'] = chain_info.get('nodes', {})
        chain_info['nodes'][node] = node_info
        boot_nodes = chain_info['boot_nodes'] = chain_info.get('boot_nodes', [])
        
        # add the node to the boot nodes
        if len(boot_nodes) > 0:
            node_info['boot_nodes'] = c.choice(boot_nodes) # choose a random boot node (at we chose one)
            cmd_kwargs += f" --bootnodes {node_info['boot_nodes']}"
    
        if node_key != None:
            cmd_kwargs += f' --node-key {node_key}'
            
        cmd_kwargs += f' --rpc-cors={rpc_cors}'

        name = f'{cls.node_prefix()}.{chain}.{node}'

        c.print(f'Starting node {node} for chain {chain} with name {name} and cmd_kwargs {cmd_kwargs}')

        if mode == 'local':
            # 
            cmd = c.pm2_start(path=cls.chain_release_path(mode=mode), 
                            name=name,
                            cmd_kwargs=cmd_kwargs,
                            refresh=refresh,
                            verbose=verbose)
            
        elif mode == 'docker':

            # run the docker image
            volumes = f'-v {base_path}:{base_path} -v {cls.spec_path}:/subspace/specs'
            net = '--net host'
            c.cmd('docker run -d --name  {name} {net} {volumes} subspace bash -c "{cmd}"', verbose=verbose)
        else: 
            raise Exception(f'unknown mode {mode}')
        
        if validator:
            # ensure you add the node to the chain_info if it is a bootnode
            node_id = cls.get_node_id(node=node, chain=chain, mode=mode)
            chain_info['boot_nodes'] +=  [f'/ip4/{ip}/tcp/{node_info["port"]}/p2p/{node_id}']
        chain_info['nodes'][node] = node_info
        cls.putc(f'chain_info.{chain}', chain_info)


        return {'success':True, 'msg': f'Node {node} is not a validator, so it will not be added to the chain'}
       
    @classmethod
    def node_exists(cls, node:str, chain:str=chain, mode:str='nonvali'):
        return node in cls.nodes(chain=chain, mode=mode)
        

    @classmethod
    def release_exists(cls):
        return c.exists(cls.chain_release_path())

    kill_chain = kill_nodes
    
    @classmethod
    def start_chain(cls, 
                    chain:str=chain, 
                    n_valis:int = 8,
                    n_nonvalis:int = 16,
                    verbose:bool = False,
                    purge_chain:bool = True,
                    refresh: bool = True,
                    trials:int = 3,
                    reuse_ports: bool = False, 
                    port_keys: list = ['port', 'rpc_port', 'ws_port'],
                    ):

        # KILL THE CHAIN
        if refresh:
            c.print(f'KILLING THE CHAIN ({chain})', color='red')
            cls.kill_chain(chain=chain)


        ## VALIDATOR NODES
        vali_node_keys  = cls.vali_node_keys(chain=chain)
        vali_nodes = list(cls.vali_node_keys(chain=chain).keys())
        if n_valis != -1:
            vali_nodes = vali_nodes[:n_valis]
        vali_node_keys = {k: vali_node_keys[k] for k in vali_nodes}
        assert len(vali_nodes) >= 2, 'There must be at least 2 vali nodes'
        # BUILD THE CHAIN SPEC AFTER SELECTING THE VALIDATOR NODES
        cls.build_spec(chain=chain, verbose=verbose, vali_node_keys=vali_node_keys)

        ## NON VALIDATOR NODES
        nonvali_node_keys = cls.nonvali_node_keys(chain=chain)
        nonvali_nodes = list(cls.nonvali_node_keys(chain=chain).keys())
        if n_nonvalis != -1:
            nonvali_nodes = nonvali_nodes[:n_valis]
        nonvali_node_keys = {k: nonvali_node_keys[k] for k in nonvali_nodes}

        # refresh the chain info in the config

        
        existing_node_ports = {'vali': [], 'nonvali': []}
        
        if reuse_ports: 
            node_infos = cls.getc(f'chain_info.{chain}.nodes')
            for node, node_info in node_infos.items():
                k = 'vali' if node_info['validator'] else 'nonvali'
                existing_node_ports[k].append([node_info[pk] for pk in port_keys])

        if refresh:
            # refresh the chain info in the config
            cls.putc(f'chain_info.{chain}', {'nodes': {}, 'boot_nodes': [], 'url': []})

        avoid_ports = []

        # START THE VALIDATOR NODES
        for node in (vali_nodes + nonvali_nodes):
            c.print(f'Starting node {node} for chain {chain}')
            name = f'{cls.node_prefix()}.{chain}.{node}'

            # BUILD THE KWARGS TO CREATE A NODE
            
            node_kwargs = {
                            'chain':chain, 
                            'node':node, 
                            'verbose':verbose,
                            'purge_chain': purge_chain,
                            'validator':  bool(node in vali_nodes),
                            }

            # get the ports for (port, rpc_port, ws_port)
            # if we are reusing ports, then pop the first ports from the existing_node_ports
            node_ports= []
            node_type = 'vali' if node_kwargs['validator'] else 'nonvali'
            if len(existing_node_ports[node_type]) > 0:
                node_ports = existing_node_ports[node_type].pop(0)
            else:
                node_ports = c.free_ports(n=3, avoid_ports=avoid_ports)
            assert  len(node_ports) == 3, f'node_ports must be of length 3, not {len(node_ports)}'

            for k, port in zip(port_keys, node_ports):
                avoid_ports.append(port)
                node_kwargs[k] = port


            fails = 0
            while trials > fails:
                try:
                    cls.start_node(**node_kwargs, refresh=refresh)
                    break
                except Exception as e:
                    c.print(f'Error starting node {node} for chain {chain}, {e}', color='red')
                    fails += 1
                    raise e
                    continue

       
    @classmethod
    def node2url(cls, network:str = network) -> str:
        assert isinstance(network, str), f'network must be a string, not {type(network)}'
        nodes =  cls.getc(f'chain_info.{network}.nodes', {})
        nodes = {k:v for k,v in nodes.items() if v['validator'] == False}
        
        assert len(nodes) > 0, f'No url found for {network}'

        node2url = {}
        for k_n, v_n in nodes.items():
            node2url[k_n] = v_n['ip'] + ':' + str(v_n['ws_port'])
        return node2url

    @classmethod
    def urls(cls, network: str = network) -> str:
        return list(cls.node2url(network=network).values())


    @classmethod
    def test_node_urls(cls, network: str = network) -> str:
        urls = cls.urls(network=network)
        for url in urls:
            c.print(f'Testing {url}...')
            c.test_url(url)
        c.print('All nodes are up and running!')


    def storage_functions(self, network=network, block_hash = None):
        self.resolve_network(network)
        return self.substrate.get_metadata_storage_functions( block_hash=block_hash)
    storage_fns = storage_functions
        

    def storage_names(self, network=network, block_hash = None):
        self.resolve_network(network)
        return [f['storage_name'] for f in self.substrate.get_metadata_storage_functions( block_hash=block_hash)]

    

if __name__ == "__main__":
    Subspace.run()