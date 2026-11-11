// Enumerate Pulse/PipeWire endpoints before falling back to native ALSA.
int _pa_get_devicelist_(pa_devicelist_t *input, pa_devicelist_t *output)
{
    memset(input, 0, sizeof(pa_devicelist_t) * 16);
    memset(output, 0, sizeof(pa_devicelist_t) * 16);
    pa_mainloop *loop = pa_mainloop_new();
    if (!loop) return -1;
    pa_context *context = pa_context_new(pa_mainloop_get_api(loop), "HamNavigator");
    if (!context) {
        pa_mainloop_free(loop);
        return -1;
    }

    int ready = 0;
    pa_context_set_state_callback(context, pa_state_cb, &ready);
    QElapsedTimer deadline;
    deadline.start();
    const auto iterate = [&]() {
        if (deadline.elapsed() >= 1500 || ready == 2) return false;
        int dispatched = pa_mainloop_iterate(loop, 0, nullptr);
        if (dispatched == 0) QThread::msleep(3);
        return dispatched >= 0;
    };
    bool ok = pa_context_connect(context, nullptr, PA_CONTEXT_NOFLAGS, nullptr) >= 0;
    while (ok && ready == 0) ok = iterate();
    ok = ok && ready == 1;
    const auto collect = [&](pa_operation *op) {
        if (!op) return false;
        while (pa_operation_get_state(op) == PA_OPERATION_RUNNING && iterate()) {}
        const bool done = pa_operation_get_state(op) == PA_OPERATION_DONE && ready == 1;
        if (!done) pa_operation_cancel(op);
        pa_operation_unref(op);
        return done;
    };
    if (ok) ok = collect(pa_context_get_sink_info_list(context, pa_sinklist_cb, output));
    if (ok) ok = collect(pa_context_get_source_info_list(context, pa_sourcelist_cb, input));
    pa_context_set_state_callback(context, nullptr, nullptr);
    pa_context_disconnect(context);
    pa_context_unref(context);
    pa_mainloop_free(loop);
    return ok ? 0 : -1;
}
