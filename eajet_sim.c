#include "eajet_sets.h"

// Initial replay state.  The printer can transition the cartridge to the next
// captured state by writing a new file 0004; the emulator detects that write
// and switches its challenge/MAC set at runtime.
#if defined(EAJET_SET_A)
#define EAJET_INITIAL_SET 0
#elif defined(EAJET_SET_B)
#define EAJET_INITIAL_SET 1
#elif defined(EAJET_SET_E)
#define EAJET_INITIAL_SET 4
#elif defined(EAJET_SET_S1)
#define EAJET_INITIAL_SET 5
#elif defined(EAJET_SET_S2)
#define EAJET_INITIAL_SET 6
#elif defined(EAJET_SET_S3)
#define EAJET_INITIAL_SET 7
#elif defined(EAJET_SET_S4)
#define EAJET_INITIAL_SET 8
#elif defined(EAJET_SET_FACTORY)
#define EAJET_INITIAL_SET 3
#else
#define EAJET_INITIAL_SET 2
#endif

static void eajet_hex(char *dst, const uint8_t *src, int n) {
    static const char digits[] = "0123456789ABCDEF";
    for (int i = 0; i < n; i++) {
        dst[i * 2] = digits[src[i] >> 4];
        dst[i * 2 + 1] = digits[src[i] & 0x0F];
    }
    dst[n * 2] = '\0';
}

static int eajet_find_file0004(const uint8_t *buf) {
    for (int i = 0; i < EAJET_SET_COUNT; i++) {
        if (memcmp(buf, eajet_file0004[i], 188) == 0) {
            return i;
        }
    }
    return -1;
}

static int eajet_find_secure(int idx, const uint8_t *buf) {
    for (int i = 0; i < EAJET_SET_COUNT; i++) {
        if (memcmp(buf, eajet_secure[i] + idx * 44, 40) == 0) {
            return i;
        }
    }
    return -1;
}

static int eajet_find_file0003(const uint8_t *buf) {
    for (int i = 0; i < EAJET_SET_COUNT; i++) {
        if (memcmp(buf, eajet_file0003[i], 32) == 0) {
            return i;
        }
    }
    return -1;
}

static void eajet_load_set(int set, uint8_t *file0004, uint8_t *file0003,
                           uint8_t secure_file[2][40]) {
    if (set < 0 || set >= EAJET_SET_COUNT) {
        return;
    }
    memcpy(file0004, eajet_file0004[set], 188);
    memcpy(file0003, eajet_file0003[set], 32);
    memcpy(secure_file[0], eajet_secure[set], 40);
    memcpy(secure_file[1], eajet_secure[set] + 44, 40);
}

static void eajet_switch_set(int found, int *active_set, uint8_t *file0004,
                             uint8_t *file0003, uint8_t secure_file[2][40],
                             const char *reason) {
    if (found < 0 || found >= EAJET_SET_COUNT) {
        return;
    }
    int old = *active_set;
    *active_set = found;
    eajet_load_set(found, file0004, file0003, secure_file);
    if (old == found) {
        // The printer restores a known state (usually A) after trying an
        // unknown candidate.  Reload it so file 0004/0003 and the secure
        // payload are consistent again.
        Dbprintf("EAJet STATE %s reload (%s)",
                 eajet_set_names[found], reason);
    } else {
        Dbprintf("EAJet STATE %s -> %s (%s)",
                 eajet_set_names[old], eajet_set_names[found], reason);
    }
}

void SimulateIso14443aTagAID(uint8_t tagType, uint16_t flags, uint8_t *uid,
                             uint8_t *ats, size_t ats_len,  uint8_t *aid, size_t aid_len,
                             uint8_t *selectaid_response, size_t selectaid_response_len,
                             uint8_t *getdata_response, size_t getdata_response_len) {

    tag_response_info_t *responses;
    uint32_t cuid = 0;
    uint8_t pages = 0;

    // command buffers
    uint8_t receivedCmd[MAX_FRAME_SIZE] = { 0x00 };
    uint8_t receivedCmdPar[MAX_PARITY_SIZE] = { 0x00 };

    // Buffers must be provided by the caller, even if lengths are 0
    if ((aid == NULL) || (selectaid_response == NULL) || (getdata_response == NULL)) {
        reply_ng(CMD_HF_MIFARE_SIMULATE, PM3_EINVARG, NULL, 0);
        return;
    }

    // The caller's buffers live in the USB packet buffer.  Copy the replay
    // payloads into local storage before any BigBuf operation.
    static uint8_t file0004[256];
    static uint8_t file0004_pending[256];
    static uint8_t secure_data[100];
    static uint8_t secure_file[2][40];  // mutable 40-byte payload of 0006/0007
    static uint8_t secure_pending[2][40];
    static uint8_t file0003[32];
    static uint8_t file0003_pending[32];
    static uint8_t file000e[32];

    int active_set = EAJET_INITIAL_SET;

    memset(file0004, 0xBF, sizeof(file0004));
    memset(file0004_pending, 0xBF, sizeof(file0004_pending));
    memset(secure_data, 0x00, sizeof(secure_data));
    memset(secure_file, 0x00, sizeof(secure_file));
    memset(secure_pending, 0x00, sizeof(secure_pending));
    memset(file0003, 0x00, sizeof(file0003));
    memset(file0003_pending, 0x00, sizeof(file0003_pending));
    memset(file000e, 0x00, sizeof(file000e));

    size_t file0004_len = selectaid_response_len;
    if (file0004_len > 188) {
        file0004_len = 188;
    }

    size_t secure_data_len = getdata_response_len;
    if (secure_data_len > sizeof(secure_data)) {
        secure_data_len = sizeof(secure_data);
    }

    // Copy the client image first so the initial state can be identified.
    memcpy(file0004, selectaid_response, file0004_len);
    memcpy(secure_data, getdata_response, secure_data_len);

    {
        int found = eajet_find_file0004(file0004);
        if (found >= 0) {
            active_set = found;
        }
    }

    // Start from the matching captured state, then let the client payload
    // override the initial image (backwards compatible with the CLI).
    memcpy(file0004, eajet_file0004[active_set], 188);
    memcpy(file0003, eajet_file0003[active_set], sizeof(file0003));
    memcpy(secure_file[0], eajet_secure[active_set], 40);
    memcpy(secure_file[1], eajet_secure[active_set] + 44, 40);

    memcpy(file0004, selectaid_response, file0004_len);
    if (selectaid_response_len >= 188 + sizeof(file0003)) {
        memcpy(file0003, selectaid_response + 188, sizeof(file0003));
    }
    if (secure_data_len >= 40) {
        memcpy(secure_file[0], secure_data, 40);
    }
    if (secure_data_len >= 84) {
        memcpy(secure_file[1], secure_data + 44, 40);
    }

    // Optional behaviour selector: the client may append one byte after the
    // 88-byte secure image.  Kept out of the APDU data so a normal 88-byte
    // replay still works exactly as before.
    //   0 = strict replay: ignore unknown file0004/secure writes
    //   1 = accept unknown file0004 writes, ignore unknown secure writes
    //   2 = store every write (previous dynamic behaviour)
    //   3 = reject unknown writes with 69 85
    //   4 = store unknown file0004/file0003, keep captured secure data/MACs
    uint8_t sim_mode = 0;
    if (secure_data_len >= 89) {
        sim_mode = secure_data[88];
    }

    memcpy(file0004_pending, file0004, sizeof(file0004_pending));
    memcpy(file0003_pending, file0003, sizeof(file0003_pending));
    memcpy(secure_pending[0], secure_file[0], 40);
    memcpy(secure_pending[1], secure_file[1], 40);
    Dbprintf("EAJet MODE %u", sim_mode);

    // Captured file 000E contents.
    static const uint8_t file000e_default[32] = {
        0xDB, 0x3D, 0x4D, 0xDA, 0x59, 0x0B, 0x1F, 0x54,
        0xD6, 0x81, 0xA9, 0x7B, 0x42, 0xAA, 0x5D, 0xEE,
        0x4F, 0xF4, 0x10, 0xCB, 0x37, 0xC3, 0xF4, 0xF6,
        0x84, 0x91, 0xC0, 0x53, 0x4D, 0x48, 0xF3, 0x0B
    };
    memcpy(file000e, file000e_default, sizeof(file000e));

    // FCIs captured from the original FM1208 applet.  Each array already
    // contains the final 90 00 status word.
    static const uint8_t fci_3f00[] = {
        0x6F, 0x15, 0x84, 0x0E, 0x31, 0x50, 0x41, 0x59,
        0x2E, 0x53, 0x59, 0x53, 0x2E, 0x44, 0x44, 0x46,
        0x30, 0x31, 0xA5, 0x03, 0x88, 0x01, 0x01, 0x90, 0x00
    };
    static const uint8_t fci_3f01[] = {
        0x6F, 0x08, 0x84, 0x00, 0xA5, 0x04, 0x9F, 0x08, 0x01, 0x02, 0x90, 0x00
    };
    static const uint8_t fci_3f0f[] = {
        0x6F, 0x2B, 0x84, 0x00, 0xA5, 0x27, 0x9F, 0x08, 0x01, 0x02, 0x9F, 0x0C, 0x20,
        0x7E, 0x9E, 0xE3, 0x99, 0xDB, 0x3A, 0xB5, 0x29, 0x01, 0x17, 0x0F, 0xDE, 0xF0,
        0x57, 0x4A, 0x26, 0x77, 0x28, 0x1B, 0xFF, 0x63, 0x00, 0x33, 0x64, 0xF7, 0x66,
        0x32, 0xD3, 0xFB, 0xD6, 0xA0, 0x3B, 0x90, 0x00
    };
    static const uint8_t fci_3f11[] = {
        0x6F, 0x02, 0x84, 0x00, 0x90, 0x00
    };
    static const uint8_t challenge[] = { 0xF2, 0x6A, 0x57, 0x4A };
    // GET CHALLENGE values captured together with the file 0006/0007 response
    // MACs in trace_full_new.txt.  The active state is selected at runtime so
    // the printer can advance the cartridge (A -> B -> C) by writing a new
    // file 0004 and secure-updating 0006/0007.

    uint16_t selected_file = 0;
    bool file000e_unlocked = false;

    //-----------------------------------------------------------------------------
    // Note: we call FpgaDownloadAndGo_keep_EM(FPGA_BITSTREAM_HF) here although the
    // FPGA isn't needed yet. iso14443a_setup() below does it otherwise, and a
    // bitstream download frees and clears BigBuf - which by then holds the
    // Emulator Memory and the precompiled anticollision responses.
    //-----------------------------------------------------------------------------
    FpgaDownloadAndGo_keep_EM(FPGA_BITSTREAM_HF);

    // free eventually allocated BigBuf memory but keep Emulator Memory
    BigBuf_free_keep_EM();

    // clear trace before allocating. The response buffers come out of the same
    // pool and BigBuf_malloc() won't hand out memory the trace still occupies.
    clear_trace();

    // Response payloads must fit within the dynamic response buffer,
    // accounting for 1-byte IBlock header + 1-byte optional CID (offset 0 or 1)
    if (selectaid_response_len + 2 > DYNAMIC_RESPONSE_BUFFER2_SIZE ||
            getdata_response_len + 2 > DYNAMIC_RESPONSE_BUFFER2_SIZE) {
        reply_ng(CMD_HF_MIFARE_SIMULATE, PM3_EINVARG, NULL, 0);
        return;
    }

    uint8_t *dynamic_response_buffer2 = BigBuf_calloc(DYNAMIC_RESPONSE_BUFFER2_SIZE);
    if (dynamic_response_buffer2 == NULL) {
        BigBuf_free_keep_EM();
        reply_ng(CMD_HF_MIFARE_SIMULATE, PM3_EMALLOC, NULL, 0);
        return;
    }

    uint8_t *dynamic_modulation_buffer2 = BigBuf_calloc(DYNAMIC_MODULATION_BUFFER2_SIZE);
    if (dynamic_modulation_buffer2 == NULL) {
        BigBuf_free_keep_EM();
        reply_ng(CMD_HF_MIFARE_SIMULATE, PM3_EMALLOC, NULL, 0);
        return;
    }

    tag_response_info_t dynamic_response_info = {
        .response = dynamic_response_buffer2,
        .response_n = 0,
        .modulation = dynamic_modulation_buffer2,
        .modulation_n = 0
    };

    if (SimulateIso14443aInit(tagType, flags, uid, ats, ats_len, &responses, &cuid, &pages, NULL) == false) {
        BigBuf_free_keep_EM();
        reply_ng(CMD_HF_MIFARE_SIMULATE, PM3_EINIT, NULL, 0);
        return;
    }

    // We need to listen to the high-frequency, peak-detected path.
    iso14443a_setup(FPGA_HF_ISO14443A_TAGSIM_LISTEN);

    iso14a_set_timeout(201400); // 106 * 19ms default *100?

    int len = 0;
    int retval = PM3_SUCCESS;
    bool odd_reply = true;
    bool logged_wupa = false;
    bool logged_anticoll = false;
    bool logged_select = false;
    bool logged_rats = false;

    set_tracing(true);
    LED_A_ON();

    // main loop
    bool finished = false;
    while (finished == false) {
        // BUTTON_PRESS check done in GetIso14443aCommandFromReader
        WDT_HIT();

        tag_response_info_t *p_response = NULL;

        // Clean receive command buffer
        if (GetIso14443aCommandFromReader(receivedCmd, sizeof(receivedCmd), receivedCmdPar, &len) == false) {
            Dbprintf("Emulator stopped. Trace length: %d ", BigBuf_get_traceLen());
            retval = PM3_EOPABORTED;
            break;
        }

        if (receivedCmd[0] == ISO14443A_CMD_REQA && len == 1) { // Received a REQUEST, but in HALTED, skip
            odd_reply = !odd_reply;
            if (odd_reply) {
                p_response = &responses[RESP_INDEX_ATQA];
            }
        } else if (receivedCmd[0] == ISO14443A_CMD_WUPA && len == 1) { // Received a WAKEUP
            p_response = &responses[RESP_INDEX_ATQA];
        } else if (receivedCmd[1] == 0x20 && receivedCmd[0] == ISO14443A_CMD_ANTICOLL_OR_SELECT && len == 2) {    // Received request for UID (cascade 1)
            p_response = &responses[RESP_INDEX_UIDC1];
        } else if (receivedCmd[1] == 0x20 && receivedCmd[0] == ISO14443A_CMD_ANTICOLL_OR_SELECT_2 && len == 2) {  // Received request for UID (cascade 2)
            p_response = &responses[RESP_INDEX_UIDC2];
        } else if (receivedCmd[1] == 0x20 && receivedCmd[0] == ISO14443A_CMD_ANTICOLL_OR_SELECT_3 && len == 2) {  // Received request for UID (cascade 3)
            p_response = &responses[RESP_INDEX_UIDC3];
        } else if (receivedCmd[1] == 0x70 && receivedCmd[0] == ISO14443A_CMD_ANTICOLL_OR_SELECT && len == 9) {    // Received a SELECT (cascade 1)
            p_response = &responses[RESP_INDEX_SAKC1];
        } else if (receivedCmd[1] == 0x70 && receivedCmd[0] == ISO14443A_CMD_ANTICOLL_OR_SELECT_2 && len == 9) {  // Received a SELECT (cascade 2)
            p_response = &responses[RESP_INDEX_SAKC2];
        } else if (receivedCmd[1] == 0x70 && receivedCmd[0] == ISO14443A_CMD_ANTICOLL_OR_SELECT_3 && len == 9) {  // Received a SELECT (cascade 3)
            p_response = &responses[RESP_INDEX_SAKC3];
        } else if (receivedCmd[0] == ISO14443A_CMD_PPS) {
            p_response = &responses[RESP_INDEX_PPS];
        } else if (receivedCmd[0] == ISO14443A_CMD_HALT && len == 4) {    // Received a HALT
            LogTrace(receivedCmd, Uart.len, Uart.startTime * 16 - DELAY_AIR2ARM_AS_TAG, Uart.endTime * 16 - DELAY_AIR2ARM_AS_TAG, Uart.parity, true);
            // Keep emulating: the printer may re-activate the same card.
            p_response = NULL;
        } else if (receivedCmd[0] == ISO14443A_CMD_RATS && len == 4) {    // Received a RATS request
            p_response = &responses[RESP_INDEX_ATS];
        } else {
            // clear old dynamic responses
            dynamic_response_info.response_n = 0;
            dynamic_response_info.modulation_n = 0;

            // Check for ISO 14443A-4 compliant commands, look at the PCB.
            uint8_t offset = 0;
            bool is_iblock = false;
            if (receivedCmd[0] == 0x0B || receivedCmd[0] == 0x0A) {
                offset = 1;
                is_iblock = true;
            } else if (receivedCmd[0] == 0x02 || receivedCmd[0] == 0x03) {
                offset = 0;
                is_iblock = true;
            }

            if (is_iblock) {
                // receivedCmd layout:
                //   | IBlock (CID) | CID | APDU Command | CRC |
                // or| IBlock (noCID) | APDU Command | CRC |
                int apdu_len = len - (1 + offset) - 2;
                uint8_t *apdu = &receivedCmd[1 + offset];
                uint8_t *out = dynamic_response_info.response + 1 + offset;

                dynamic_response_info.response[0] = receivedCmd[0];
                dynamic_response_info.response[1] = 0x00;

                if (apdu_len < 4) {
                    out[0] = 0x6A;
                    out[1] = 0x80;
                    dynamic_response_info.response_n = 3 + offset;
                } else {
                    uint8_t cla = apdu[0];
                    uint8_t ins = apdu[1];
                    uint8_t p1 = apdu[2];
                    uint8_t p2 = apdu[3];

                    Dbprintf("EAJet APDU %02X %02X %02X %02X len=%d", cla, ins, p1, p2, apdu_len);

                    if (cla == 0x00 && ins == 0xA4) {  // SELECT FILE
                        uint8_t lc = (apdu_len >= 5) ? apdu[4] : 0;
                        if (apdu_len < 5 + (int)lc) {
                            out[0] = 0x6A;
                            out[1] = 0x80;
                            dynamic_response_info.response_n = 3 + offset;
                        } else {
                            uint16_t fid = 0;
                            if (lc >= 2) {
                                fid = ((uint16_t)apdu[5 + lc - 2] << 8) | apdu[5 + lc - 1];
                            }
                            selected_file = fid;
                            Dbprintf("EAJet SEL %04X", fid);
                            if (fid == 0x3F00) {
                                file000e_unlocked = false;
                            }
                            if (fid == 0x3F00) {
                                memcpy(out, fci_3f00, sizeof(fci_3f00));
                                dynamic_response_info.response_n = sizeof(fci_3f00) + 1 + offset;
                            } else if (fid == 0x3F01 || fid == 0x3F02) {
                                memcpy(out, fci_3f01, sizeof(fci_3f01));
                                dynamic_response_info.response_n = sizeof(fci_3f01) + 1 + offset;
                            } else if (fid == 0x3F0F) {
                                memcpy(out, fci_3f0f, sizeof(fci_3f0f));
                                dynamic_response_info.response_n = sizeof(fci_3f0f) + 1 + offset;
                            } else if (fid == 0x3F11) {
                                memcpy(out, fci_3f11, sizeof(fci_3f11));
                                dynamic_response_info.response_n = sizeof(fci_3f11) + 1 + offset;
                            } else if (fid == 0x0003 || fid == 0x0004 || fid == 0x0005 ||
                                       fid == 0x0006 || fid == 0x0007 || fid == 0x000E ||
                                       fid == 0x001D) {
                                out[0] = 0x90;
                                out[1] = 0x00;
                                dynamic_response_info.response_n = 3 + offset;
                            } else {
                                out[0] = 0x6A;
                                out[1] = 0x82;
                                dynamic_response_info.response_n = 3 + offset;
                            }
                        }
                    } else if (cla == 0x00 && ins == 0x84) {  // GET CHALLENGE
                        const uint8_t *ch = challenge;
                        if (selected_file == 0x0006) {
                            ch = eajet_ch6[active_set];
                        } else if (selected_file == 0x0007) {
                            ch = eajet_ch7[active_set];
                        }
                        memcpy(out, ch, sizeof(challenge));
                        out[sizeof(challenge)] = 0x90;
                        out[sizeof(challenge) + 1] = 0x00;
                        dynamic_response_info.response_n = sizeof(challenge) + 3 + offset;
                        Dbprintf("EAJet GC file=%04X set=%s ch=%02X%02X%02X%02X",
                                 selected_file, eajet_set_names[active_set],
                                 ch[0], ch[1], ch[2], ch[3]);
                    } else if (cla == 0x00 && ins == 0x82) {  // EXTERNAL AUTHENTICATE
                        if (p2 == 0x19) {
                            file000e_unlocked = true;
                        }
                        out[0] = 0x90;
                        out[1] = 0x00;
                        dynamic_response_info.response_n = 3 + offset;
                    } else if (cla == 0x00 && ins == 0x20) {  // VERIFY
                        out[0] = 0x90;
                        out[1] = 0x00;
                        dynamic_response_info.response_n = 3 + offset;
                    } else if (cla == 0x00 && ins == 0xB0) {  // READ BINARY
                        uint16_t off = ((uint16_t)p1 << 8) | p2;
                        uint16_t le = (apdu_len >= 5) ? apdu[4] : 0;
                        if (le == 0) {
                            le = 256;
                        }
                        Dbprintf("EAJet READ file=%04X off=%04X le=%u", selected_file, off, le);
                        const uint8_t *src = NULL;
                        uint16_t src_len = 0;
                        if (selected_file == 0x0004 || selected_file == 0x0005) {
                            src = file0004;
                            src_len = (uint16_t)file0004_len;
                        } else if (selected_file == 0x0003 || selected_file == 0x001D) {
                            src = file0003;
                            src_len = sizeof(file0003);
                        } else if (selected_file == 0x000E && file000e_unlocked) {
                            src = file000e;
                            src_len = sizeof(file000e);
                        }
                        if (src == NULL) {
                            out[0] = 0x69;
                            out[1] = 0x82;
                            dynamic_response_info.response_n = 3 + offset;
                        } else if (off >= src_len) {
                            out[0] = 0x6B;
                            out[1] = 0x00;
                            dynamic_response_info.response_n = 3 + offset;
                        } else {
                            uint16_t n = src_len - off;
                            if (n > le) {
                                n = le;
                            }
                            memcpy(out, src + off, n);
                            out[n] = 0x90;
                            out[n + 1] = 0x00;
                            dynamic_response_info.response_n = n + 3 + offset;
                        }
                    } else if (cla == 0x00 && ins == 0xD6) {  // UPDATE BINARY
                        uint8_t lc = (apdu_len >= 5) ? apdu[4] : 0;
                        if (apdu_len < 5 + (int)lc) {
                            out[0] = 0x6A;
                            out[1] = 0x80;
                            dynamic_response_info.response_n = 3 + offset;
                        } else {
                            uint16_t off = ((uint16_t)p1 << 8) | p2;
                            if (selected_file == 0x0004 || selected_file == 0x0005) {
                                bool wr4_ok = true;
                                if (off < file0004_len) {
                                    uint16_t n = lc;
                                    if (n > file0004_len - off) {
                                        n = file0004_len - off;
                                    }
                                    memcpy(file0004_pending + off, apdu + 5, n);
                                    if (off + n >= file0004_len) {
                                        int found = eajet_find_file0004(file0004_pending);
                                        Dbprintf("EAJet WR4 end tail=%02X%02X found=%d mode=%u",
                                                 file0004_pending[186], file0004_pending[187],
                                                 found, sim_mode);
                                        if (found >= 0) {
                                            memcpy(file0004, file0004_pending, file0004_len);
                                            eajet_switch_set(found, &active_set, file0004,
                                                             file0003, secure_file, "file0004");
                                            memcpy(file0004_pending, file0004, sizeof(file0004_pending));
                                            memcpy(file0003_pending, file0003, sizeof(file0003_pending));
                                            memcpy(secure_pending[0], secure_file[0], 40);
                                            memcpy(secure_pending[1], secure_file[1], 40);
                                        } else if (sim_mode == 1 || sim_mode == 2 || sim_mode == 4) {
                                            // Keep the printer's new image so a
                                            // read-back matches, but leave the
                                            // active challenge/MAC set alone.
                                            memcpy(file0004, file0004_pending, file0004_len);
                                            Dbprintf("EAJet WR4 stored unknown (mode=%u)", sim_mode);
                                        } else {
                                            // Strict replay: the card appears
                                            // unchanged.  This keeps file0004,
                                            // file0003 and the secure payload
                                            // from the same captured set.
                                            memcpy(file0004_pending, file0004, sizeof(file0004_pending));
                                            Dbprintf("EAJet WR4 ignored unknown (mode=%u)", sim_mode);
                                            if (sim_mode == 3) {
                                                wr4_ok = false;
                                            }
                                        }
                                    }
                                }
                                if (wr4_ok) {
                                    out[0] = 0x90;
                                    out[1] = 0x00;
                                } else {
                                    out[0] = 0x69;
                                    out[1] = 0x85;
                                }
                                dynamic_response_info.response_n = 3 + offset;
                            } else if (selected_file == 0x0003 || selected_file == 0x001D) {
                                uint16_t n = 0;
                                bool wr3_ok = true;
                                if (off < sizeof(file0003)) {
                                    n = lc;
                                    if (n > sizeof(file0003) - off) {
                                        n = sizeof(file0003) - off;
                                    }
                                    memcpy(file0003_pending + off, apdu + 5, n);
                                }
                                char data3_hex[65];
                                eajet_hex(data3_hex, apdu + 5, n > 32 ? 32 : n);
                                Dbprintf("EAJet WR3 file=%04X off=%04X n=%u data=%s mode=%u",
                                         selected_file, off, n, data3_hex, sim_mode);
                                if (off + n >= sizeof(file0003)) {
                                    int found = eajet_find_file0003(file0003_pending);
                                    Dbprintf("EAJet WR3 end found=%d:", found);
                                    Dbhexdump(sizeof(file0003), file0003_pending, false);
                                    if (found >= 0) {
                                        memcpy(file0003, file0003_pending, sizeof(file0003));
                                    } else if (sim_mode == 2 || sim_mode == 4) {
                                        memcpy(file0003, file0003_pending, sizeof(file0003));
                                        Dbprintf("EAJet WR3 stored unknown (mode=%u)", sim_mode);
                                    } else {
                                        memcpy(file0003_pending, file0003, sizeof(file0003_pending));
                                        Dbprintf("EAJet WR3 ignored unknown (mode=%u)", sim_mode);
                                        if (sim_mode == 3) {
                                            wr3_ok = false;
                                        }
                                    }
                                }
                                if (wr3_ok) {
                                    out[0] = 0x90;
                                    out[1] = 0x00;
                                } else {
                                    out[0] = 0x69;
                                    out[1] = 0x85;
                                }
                                dynamic_response_info.response_n = 3 + offset;
                            } else if (selected_file == 0x000E) {
                                out[0] = 0x90;
                                out[1] = 0x00;
                                dynamic_response_info.response_n = 3 + offset;
                            } else {
                                out[0] = 0x69;
                                out[1] = 0x82;
                                dynamic_response_info.response_n = 3 + offset;
                            }
                        }
                    } else if (cla == 0x04 && ins == 0xB0) {  // SECURE READ
                        int idx = -1;
                        if (selected_file == 0x0006) {
                            idx = 0;
                        } else if (selected_file == 0x0007) {
                            idx = 1;
                        }
                        if (idx < 0) {
                            out[0] = 0x69;
                            out[1] = 0x82;
                            dynamic_response_info.response_n = 3 + offset;
                        } else {
                            if (apdu_len >= 9) {
                                Dbprintf("EAJet SECREAD file=%04X cmd=%02X%02X%02X%02X",
                                         selected_file, apdu[5], apdu[6], apdu[7], apdu[8]);
                            }
                            const uint8_t *mac = eajet_secure[active_set] + idx * 44 + 40;
                            memcpy(out, secure_file[idx], 40);
                            memcpy(out + 40, mac, 4);
                            out[44] = 0x90;
                            out[45] = 0x00;
                            dynamic_response_info.response_n = 44 + 3 + offset;
                            Dbprintf("EAJet SECREAD resp file=%04X set=%s mac=%02X%02X%02X%02X",
                                     selected_file, eajet_set_names[active_set],
                                     mac[0], mac[1], mac[2], mac[3]);
                        }
                    } else if (cla == 0x04 && ins == 0xD6) {  // SECURE UPDATE
                        uint8_t lc = (apdu_len >= 5) ? apdu[4] : 0;
                        int idx = -1;
                        if (selected_file == 0x0006) {
                            idx = 0;
                        } else if (selected_file == 0x0007) {
                            idx = 1;
                        }
                        if (idx < 0 || apdu_len < 5 + (int)lc || lc < 4) {
                            out[0] = 0x6A;
                            out[1] = 0x80;
                            dynamic_response_info.response_n = 3 + offset;
                        } else {
                            uint16_t off = ((uint16_t)p1 << 8) | p2;
                            uint16_t n = lc - 4;
                            bool secupd_ok = true;
                            if (off < 40) {
                                if (n > 40 - off) {
                                    n = 40 - off;
                                }
                                memcpy(secure_pending[idx] + off, apdu + 5, n);
                            }
                            int found = -1;
                            if (off + n >= 40) {
                                found = eajet_find_secure(idx, secure_pending[idx]);
                                if (found >= 0) {
                                    memcpy(secure_file[idx], secure_pending[idx], 40);
                                    eajet_switch_set(found, &active_set, file0004,
                                                     file0003, secure_file, "secure");
                                    memcpy(file0004_pending, file0004, sizeof(file0004_pending));
                                    memcpy(file0003_pending, file0003, sizeof(file0003_pending));
                                    memcpy(secure_pending[0], secure_file[0], 40);
                                    memcpy(secure_pending[1], secure_file[1], 40);
                                } else if (sim_mode == 2) {
                                    // Previous behaviour: keep the printer's
                                    // payload, but the active-set MAC will not
                                    // match it.
                                    memcpy(secure_file[idx], secure_pending[idx], 40);
                                    Dbprintf("EAJet SECUPD stored unknown (mode=%u)", sim_mode);
                                } else {
                                    // Strict replay: keep the captured payload
                                    // and its matching response MAC.
                                    memcpy(secure_pending[idx], secure_file[idx], 40);
                                    Dbprintf("EAJet SECUPD ignored unknown (mode=%u)", sim_mode);
                                    if (sim_mode == 3) {
                                        secupd_ok = false;
                                    }
                                }
                            }
                            if (secupd_ok) {
                                out[0] = 0x90;
                                out[1] = 0x00;
                            } else {
                                out[0] = 0x69;
                                out[1] = 0x85;
                            }
                            dynamic_response_info.response_n = 3 + offset;
                            char data_hex[41];
                            eajet_hex(data_hex, apdu + 5, n > 20 ? 20 : n);
                            Dbprintf("EAJet SECUPD file=%04X off=%04X n=%u found=%d set=%s mode=%u data=%s",
                                     selected_file, off, n, found,
                                     eajet_set_names[active_set], sim_mode, data_hex);
                        }
                    } else {
                        out[0] = 0x6A;
                        out[1] = 0x82;
                        dynamic_response_info.response_n = 3 + offset;
                    }
                }
            } else if (receivedCmd[0] == 0xCA || receivedCmd[0] == 0xC2) {  // S-block deselect
                uint8_t s_offset = (receivedCmd[0] & 0x08) ? 1 : 0;
                dynamic_response_info.response[0] = receivedCmd[0];
                dynamic_response_info.response[1] = s_offset ? receivedCmd[1] : 0x00;
                dynamic_response_info.response_n = 1 + s_offset;
            } else {
                // Never seen this PCB before
                LogTrace(receivedCmd, Uart.len, Uart.startTime * 16 - DELAY_AIR2ARM_AS_TAG, Uart.endTime * 16 - DELAY_AIR2ARM_AS_TAG, Uart.parity, true);
                if (g_dbglevel >= DBG_DEBUG) {
                    Dbprintf("Received unknown command (len=%d):", len);
                    Dbhexdump(len, receivedCmd, false);
                }
                if ((receivedCmd[0] & 0x10) == 0x10) {
                    Dbprintf("Warning, reader sent a chained command but we lack support for it. Ignoring command.");
                }
                // Do not respond
                dynamic_response_info.response_n = 0;
            }

            if (dynamic_response_info.response_n > 0) {
                // Copy the CID from the reader query
                if (offset > 0) {
                    dynamic_response_info.response[1] = receivedCmd[1];
                }

                // Add CRC bytes, always used in ISO 14443A-4 compliant cards
                AddCrc14A(dynamic_response_info.response, dynamic_response_info.response_n);
                dynamic_response_info.response_n += 2;

                if (prepare_tag_modulation(&dynamic_response_info, DYNAMIC_MODULATION_BUFFER2_SIZE) == false) {
                    if (g_dbglevel >= DBG_DEBUG) {
                        DbpString("Error preparing tag response");
                    }
                    LogTrace(receivedCmd, Uart.len, Uart.startTime * 16 - DELAY_AIR2ARM_AS_TAG, Uart.endTime * 16 - DELAY_AIR2ARM_AS_TAG, Uart.parity, true);
                    break;
                }
                p_response = &dynamic_response_info;
            }
        }

        // Send response
        EmSendPrecompiledCmd(p_response);

        // RF-diagnostic markers.  These are logged *after* the response has
        // been transmitted so they cannot delay REQA/anticollision replies.
        // Each marker is printed once per emulation run.
        if (!logged_wupa && len == 1 &&
                (receivedCmd[0] == ISO14443A_CMD_REQA || receivedCmd[0] == ISO14443A_CMD_WUPA)) {
            logged_wupa = true;
            Dbprintf("EAJet RF %s", receivedCmd[0] == ISO14443A_CMD_REQA ? "REQA" : "WUPA");
        }
        if (!logged_anticoll && len == 2 && receivedCmd[1] == 0x20 &&
                receivedCmd[0] >= ISO14443A_CMD_ANTICOLL_OR_SELECT &&
                receivedCmd[0] <= ISO14443A_CMD_ANTICOLL_OR_SELECT_3) {
            logged_anticoll = true;
            Dbprintf("EAJet RF ANTICOLL %02X", receivedCmd[0]);
        }
        if (!logged_select && len == 9 &&
                receivedCmd[0] >= ISO14443A_CMD_ANTICOLL_OR_SELECT &&
                receivedCmd[0] <= ISO14443A_CMD_ANTICOLL_OR_SELECT_3) {
            logged_select = true;
            Dbprintf("EAJet RF SELECT %02X", receivedCmd[0]);
        }
        if (!logged_rats && receivedCmd[0] == ISO14443A_CMD_RATS && len == 4) {
            logged_rats = true;
            Dbprintf("EAJet RATS");
        }
    }

    switch_off();

    set_tracing(false);
    BigBuf_free_keep_EM();

    reply_ng(CMD_HF_MIFARE_SIMULATE, retval, NULL, 0);
}
