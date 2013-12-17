package org.ovirt.vdsm.jsonrpc.client.reactors;

import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.ClosedChannelException;
import java.nio.channels.SelectionKey;
import java.nio.channels.Selector;
import java.nio.channels.SocketChannel;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

import javax.net.ssl.SSLEngine;
import javax.net.ssl.SSLException;

import org.apache.commons.logging.Log;
import org.apache.commons.logging.LogFactory;
import org.ovirt.vdsm.jsonrpc.client.ClientConnectionException;

/**
 * <code>ReactorClient</code> implementation to provide encrypted communication.
 *
 */
public class SSLClient extends ReactorClient {
    private static Log log = LogFactory.getLog(SSLClient.class);
    private final ExecutorService executorService;
    private final Selector selector;
    private final SSLEngine engine;
    private SSLEngineNioHelper nioEngine;

    public SSLClient(Reactor reactor, Selector selector,
            String hostname, int port, SSLEngine engine) throws ClientConnectionException {
        super(reactor, hostname, port);
        this.executorService = Executors.newCachedThreadPool();
        this.selector = selector;
        this.engine = engine;
    }

    public SSLClient(Reactor reactor, Selector selector, String hostname, int port,
            SSLEngine engine, SocketChannel socketChannel) throws ClientConnectionException {
        super(reactor, hostname, port);
        this.executorService = Executors.newCachedThreadPool();
        this.selector = selector;
        this.engine = engine;
        channel = socketChannel;

        postConnect();
    }

    @Override
    public void updateInterestedOps() throws ClientConnectionException {
        if (outbox.isEmpty() && (nioEngine == null || !nioEngine.handshakeInProgress())) {
            getSelectionKey().interestOps(SelectionKey.OP_READ);
        } else {
            getSelectionKey().interestOps(SelectionKey.OP_READ | SelectionKey.OP_WRITE);
        }
    }

    private Runnable pendingOperations() throws IOException {
        if (nioEngine == null) {
            return null;
        }

        return nioEngine.process();

    }

    @Override
    void read(ByteBuffer buff) throws IOException {
        if (nioEngine != null) {
            nioEngine.read(buff);
        } else {
            channel.read(buff);
        }
    }

    @Override
    void write(ByteBuffer buff) throws IOException {
        if (nioEngine != null) {
            nioEngine.write(buff);
        } else {
            channel.write(buff);
        }
    }

    @Override
    public void process() throws IOException, ClientConnectionException {
        final Runnable op = pendingOperations();
        if (op != null) {
            key.interestOps(0);
            this.executorService.execute(new Runnable() {
                @Override
                public void run() {
                    try {
                        op.run();
                        updateInterestedOps();
                        selector.wakeup();
                    } catch (ClientConnectionException e) {
                        log.error("Unable to process messages", e);
                    }
                }
            });
        }

        if (nioEngine != null && nioEngine.handshakeInProgress()) {
            return;
        }
        super.process();
    }

    @Override
    void postConnect() throws ClientConnectionException {
        try {
            this.nioEngine = new SSLEngineNioHelper(channel, engine);
            this.nioEngine.beginHandshake();

            int interestedOps = SelectionKey.OP_READ;
            reactor.wakeup();
            key = this.channel.register(selector, interestedOps |= SelectionKey.OP_WRITE, this);
        } catch (ClosedChannelException | SSLException e) {
            log.error("Connection issues during ssl client creation", e);
            throw new ClientConnectionException(e);
        }
    }
}
