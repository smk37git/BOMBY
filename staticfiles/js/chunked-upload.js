class ChunkedUploader {
    constructor(options = {}) {
        this.chunkSize = options.chunkSize || 1024 * 1024; // 1MB default chunk size
        this.retries = options.retries || 3;
        this.concurrentUploads = options.concurrentUploads || 3;
        this.csrfToken = document.querySelector('[name=csrfmiddlewaretoken]').value;
        this.activeUploads = 0;
        this.uploadQueue = [];
        this.onProgress = options.onProgress || (() => {});
        this.onComplete = options.onComplete || (() => {});
        this.onError = options.onError || (() => {});
    }

    async uploadFile(file, metadata = {}) {
        // Create a unique ID for this file upload
        const uploadId = Date.now() + '-' + Math.random().toString(36).substr(2, 9);
        
        // Initialize the upload
        try {
            await this._initUpload(uploadId, file, metadata);
            
            // Split file into chunks
            const chunks = this._createChunks(file);
            
            // Upload chunks
            const uploadPromises = [];
            for (let i = 0; i < chunks.length; i++) {
                // Create a task and add to queue
                const task = {
                    uploadId,
                    chunk: chunks[i],
                    index: i,
                    total: chunks.length,
                    filename: file.name,
                    metadata
                };
                this.uploadQueue.push(task);
            }
            
            // Start processing queue
            this._processQueue();
            
            return uploadId;
        } catch (error) {
            this.onError(error, file);
            throw error;
        }
    }

    _createChunks(file) {
        const chunks = [];
        let start = 0;
        
        while (start < file.size) {
            const end = Math.min(start + this.chunkSize, file.size);
            chunks.push(file.slice(start, end));
            start = end;
        }
        
        return chunks;
    }

    async _initUpload(uploadId, file, metadata) {
        const formData = new FormData();
        formData.append('action', 'init');
        formData.append('upload_id', uploadId);
        formData.append('filename', file.name);
        formData.append('filesize', file.size);
        formData.append('filetype', file.type);
        
        // Add any metadata
        for (const [key, value] of Object.entries(metadata)) {
            formData.append(key, value);
        }
        
        const response = await fetch('/store/upload/chunk/', {
            method: 'POST',
            headers: {
                'X-CSRFToken': this.csrfToken
            },
            body: formData
        });
        
        if (!response.ok) {
            throw new Error('Failed to initialize upload');
        }
        
        return await response.json();
    }

    async _uploadChunk(task, retryCount = 0) {
        try {
            const { uploadId, chunk, index, total, filename, metadata } = task;
            const formData = new FormData();
            formData.append('action', 'upload');
            formData.append('upload_id', uploadId);
            formData.append('chunk_index', index);
            formData.append('total_chunks', total);
            formData.append('chunk', chunk, `${filename}.part${index}`);
            
            const response = await fetch('/store/upload/chunk/', {
                method: 'POST',
                headers: {
                    'X-CSRFToken': this.csrfToken
                },
                body: formData
            });
            
            if (!response.ok) {
                throw new Error(`Failed to upload chunk ${index}`);
            }
            
            // Report progress
            this.onProgress({
                uploadId,
                filename,
                chunkIndex: index,
                totalChunks: total,
                percentage: Math.round(((index + 1) / total) * 100)
            });
            
            // Check if all chunks are uploaded
            if (index === total - 1) {
                await this._finalizeUpload(uploadId, filename, metadata);
            }
            
            return await response.json();
        } catch (error) {
            if (retryCount < this.retries) {
                // Retry the upload
                return await this._uploadChunk(task, retryCount + 1);
            } else {
                throw error;
            }
        } finally {
            this.activeUploads--;
            this._processQueue();
        }
    }

    async _finalizeUpload(uploadId, filename, metadata) {
        const formData = new FormData();
        formData.append('action', 'finalize');
        formData.append('upload_id', uploadId);
        formData.append('filename', filename);
        
        // Add any metadata
        for (const [key, value] of Object.entries(metadata)) {
            formData.append(key, value);
        }
        
        const response = await fetch('/store/upload/chunk/', {
            method: 'POST',
            headers: {
                'X-CSRFToken': this.csrfToken
            },
            body: formData
        });
        
        if (!response.ok) {
            throw new Error('Failed to finalize upload');
        }
        
        const result = await response.json();
        this.onComplete(result, filename);
        return result;
    }

    _processQueue() {
        // Process items in the queue if we're under our concurrent upload limit
        while (this.uploadQueue.length > 0 && this.activeUploads < this.concurrentUploads) {
            const task = this.uploadQueue.shift();
            this.activeUploads++;
            this._uploadChunk(task).catch((error) => {
                this.onError(error, task.filename);
            });
        }
    }
}