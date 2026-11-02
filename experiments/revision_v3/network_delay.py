"""Task-local TCP stream delay; no host networking configuration changes."""
from pathlib import Path
import asyncio,json,os,re,signal,socket,statistics,time

class DelayNetwork:
    def __init__(self,rtt_ms):
        self.delay=rtt_ms/2000
        self.listeners=[];self.tasks=set();self.writers=set()
        self.stats={"requested_added_rtt_ms":rtt_ms,"connections":0,"bytes_relayed":0,"max_direction_queue_bytes":0,"backpressure_events":0}

    async def direction(self,reader,writer):
        queue=asyncio.Queue(maxsize=128);queued=0
        async def receive():
            nonlocal queued
            while True:
                data=await reader.read(65536)
                if not data:await queue.put(None);break
                arrival=asyncio.get_running_loop().time()
                if queue.full():self.stats["backpressure_events"]+=1
                await queue.put((arrival+self.delay,data))
                queued+=len(data)
                self.stats["max_direction_queue_bytes"]=max(self.stats["max_direction_queue_bytes"],queued)
        async def transmit():
            nonlocal queued
            while True:
                item=await queue.get()
                if item is None:
                    if writer.can_write_eof():writer.write_eof()
                    return
                deadline,data=item;remaining=deadline-asyncio.get_running_loop().time()
                if remaining>0:await asyncio.sleep(remaining)
                writer.write(data);await writer.drain()
                queued-=len(data);self.stats["bytes_relayed"]+=len(data)
        tasks=[asyncio.create_task(receive()),asyncio.create_task(transmit())]
        try:await asyncio.gather(*tasks)
        finally:
            for task in tasks:
                if not task.done():task.cancel()
            await asyncio.gather(*tasks,return_exceptions=True)

    async def connection(self,reader,writer,target):
        self.stats["connections"]+=1;self.writers.add(writer)
        outgoing=None
        try:
            # MP-SPDZ peers can start milliseconds apart. Retry only the
            # explicitly assigned loopback target while its server binds.
            for attempt in range(200):
                try:upstream,outgoing=await asyncio.open_connection("127.0.0.1",target);break
                except ConnectionRefusedError:
                    if attempt==199:raise
                    await asyncio.sleep(.01)
            self.writers.add(outgoing)
            for stream in (writer,outgoing):stream.get_extra_info("socket").setsockopt(socket.IPPROTO_TCP,socket.TCP_NODELAY,1)
            await asyncio.gather(self.direction(reader,outgoing),self.direction(upstream,writer))
        except (ConnectionError,asyncio.CancelledError):pass
        finally:
            for stream in (writer,outgoing):
                if stream is not None:
                    stream.close();self.writers.discard(stream)

    async def listen(self,target):
        def accept(reader,writer):
            task=asyncio.create_task(self.connection(reader,writer,target))
            self.tasks.add(task);task.add_done_callback(self.tasks.discard)
        server=await asyncio.start_server(accept,"127.0.0.1",0)
        self.listeners.append(server)
        return server.sockets[0].getsockname()[1]

    async def close(self):
        for server in self.listeners:server.close()
        for server in self.listeners:await server.wait_closed()
        for writer in list(self.writers):writer.close()
        pending=list(self.tasks)
        for task in pending:task.cancel()
        await asyncio.gather(*pending,return_exceptions=True)

async def echo_calibration(rtt_ms):
    async def echo(reader,writer):
        try:
            while data:=await reader.read(65536):writer.write(data);await writer.drain()
        finally:writer.close()
    server=await asyncio.start_server(echo,"127.0.0.1",0)
    network=DelayNetwork(rtt_ms)
    try:
        port=await network.listen(server.sockets[0].getsockname()[1])
        reader,writer=await asyncio.open_connection("127.0.0.1",port)
        samples=[]
        for i in range(22):
            started=time.perf_counter();writer.write(b"x"*64);await writer.drain()
            assert await reader.readexactly(64)==b"x"*64
            if i>=2:samples.append(1000*(time.perf_counter()-started))
        writer.close();await writer.wait_closed()
        result={"target_added_rtt_ms":rtt_ms,"echo_rtt_ms":samples,"echo_median_ms":statistics.median(samples),"echo_min_ms":min(samples),"echo_max_ms":max(samples)}
        assert result["echo_median_ms"]>=rtt_ms*.9
        assert result["echo_median_ms"]<=rtt_ms+max(15,rtt_ms*.25)
        return result
    finally:await network.close();server.close();await server.wait_closed()

async def run_mpc(runtime,program,prime,rtt_ms,log,timeout):
    runtime=Path(runtime);log=Path(log);log.parent.mkdir(parents=True,exist_ok=True)
    folder=log.with_suffix("");folder.mkdir(exist_ok=True)
    reserved=[];real=[];network=DelayNetwork(rtt_ms);processes=[];streams=[]
    started=time.monotonic();cpu=time.process_time();failure=None
    environment=dict(os.environ)
    environment["LD_LIBRARY_PATH"]=str(runtime)+os.pathsep+environment.get("LD_LIBRARY_PATH","")
    try:
        for _ in range(5):
            reservation=socket.socket();reservation.bind(("127.0.0.1",0))
            reserved.append(reservation);real.append(reservation.getsockname()[1])
        hostfiles=[]
        for party in range(5):
            ports=[real[target] if target==party else await network.listen(real[target]) for target in range(5)]
            path=folder/f"hosts_P{party}.txt"
            path.write_text("\n".join(f"127.0.0.1:{port}" for port in ports)+"\n");hostfiles.append(path)
        for reservation in reserved:reservation.close()
        for party in range(5):
            stream=(folder/f"party{party}.log").open("w");streams.append(stream)
            argv=["/usr/bin/time","-v",str(runtime/"shamir-party.x"),str(party),program,"--prime",str(prime),"-N","5","-T","2","-ip",str(hostfiles[party]),"-pn",str(real[party])]
            process=await asyncio.create_subprocess_exec(*argv,cwd=runtime,env=environment,stdout=stream,stderr=asyncio.subprocess.STDOUT,start_new_session=True)
            processes.append(process)
        async def wait(process):
            code=await process.wait()
            if code:raise RuntimeError(f"Owned MPC process{process.pid} returned{code}")
        await asyncio.wait_for(asyncio.gather(*(wait(process) for process in processes)),timeout)
    except BaseException as error:failure=error
    finally:
        for reservation in reserved:reservation.close()
        for process in processes:
            if process.returncode is None:
                try:os.killpg(process.pid,signal.SIGTERM)
                except ProcessLookupError:pass
        for process in processes:
            if process.returncode is None:
                try:await asyncio.wait_for(process.wait(),5)
                except asyncio.TimeoutError:
                    try:os.killpg(process.pid,signal.SIGKILL)
                    except ProcessLookupError:pass
                    await process.wait()
        for stream in streams:stream.close()
        await network.close()
        parts=[(folder/f"party{party}.log").read_text(errors="replace") for party in range(len(streams))]
        rss=[int(value) for part in parts for value in re.findall(r"Maximum resident set size \(kbytes\): (\d+)",part)]
        with log.open("w") as stream:
            stream.write(json.dumps({"task_local_tcp_delay":True,"rtt_ms":rtt_ms,"program":program,"party_logs":str(folder)})+"\n")
            if rss:stream.write(f"Maximum resident set size (kbytes): {max(rss)}\n")
            for party,part in enumerate(parts):stream.write(f"\nPARTY{party}\n"+part)
        network.stats.update({"wall_seconds":time.monotonic()-started,"relay_controller_cpu_seconds":time.process_time()-cpu,"failure":repr(failure) if failure else None,"mechanism":"User-space per-direction stream release at arrival+RTT/2; loopback, no bandwidth/loss model"})
        log.with_suffix(".network.json").write_text(json.dumps(network.stats,indent=2))
    if failure:raise failure
    return time.monotonic()-started
